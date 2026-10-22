"""Desktop runtime pack locks (desktop roadmap §4.3, DT-1.2; gate item 4 in §6).

    python scripts/desktop_locks.py derive          # Torch layers and overlays from the service locks
    python scripts/desktop_locks.py compile-macos   # the macOS locks, compiled with uv for aarch64-apple-darwin
    python scripts/desktop_locks.py wheelhouse      # build wheels for source-only packages (release time)
    python scripts/desktop_locks.py packfiles       # resolve every runtime to exact wheels (network)
    python scripts/desktop_locks.py check           # the release gate: nothing above is stale or inconsistent

Every runtime pack in ``src/app/models/catalog.json`` names its lock and its file
list. Overlays name the service lock they come from (``source_lock``); a Torch
layer is the ``torch``/``torchaudio`` blocks every overlay standing on it shares.
Run ``derive`` after changing a service lock, then ``packfiles``; ``check`` fails
until both are done.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.models import catalog as model_catalog  # noqa: E402
from app.models.locks import (  # noqa: E402
    LockError, check_overlay, check_torch_pins, derive_overlay, parse_lock, read_lock, torch_layer_lock,
)
from app.models.packfiles import (  # noqa: E402
    PackFilesError, check_pack_files, load_pack_files, resolve, sdist_for, write_pack_files,
)

DESKTOP = ROOT / "requirements" / "desktop"
WHEELHOUSE = DESKTOP / "wheelhouse"
# The macOS locks: compiled from these inputs, since pip-compile only writes the current platform's dependencies.
MACOS_INPUTS = {
    "requirements/desktop/tts.macos-arm64.full.lock.txt": "requirements/desktop/tts.macos-arm64.in",
    "requirements/desktop/stt-mlx.macos-arm64.lock.txt": "requirements/desktop/stt-mlx.macos-arm64.in",
}


def _catalog() -> model_catalog.Catalog:
    return model_catalog.load()


def _overlays_on(catalog: model_catalog.Catalog, layer_id: str) -> list[model_catalog.RuntimePack]:
    return [catalog.runtime(runtime_id) for runtime_id in catalog.dependents(layer_id)]


def derive() -> int:
    catalog = _catalog()
    for pack in catalog.runtimes.values():
        if pack.kind != "torch-layer":
            continue
        overlays = [item for item in _overlays_on(catalog, pack.id) if (ROOT / item.source_lock).is_file()]
        if not overlays:
            print(f"skip {pack.id}: no source lock yet")
            continue
        sources = {item.source_lock: read_lock(ROOT / item.source_lock) for item in overlays}
        (ROOT / pack.lock).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / pack.lock).write_text(torch_layer_lock(sources), encoding="utf-8")
        print(f"wrote {pack.lock}")
        for item in overlays:
            text = derive_overlay(sources[item.source_lock], source_name=item.source_lock)
            (ROOT / item.lock).write_text(text, encoding="utf-8")
            print(f"wrote {item.lock}")
    return 0


def compile_macos() -> int:
    uv = shutil.which("uv")
    if uv is None:
        print("uv is required: it compiles locks for another platform", file=sys.stderr)
        return 2
    for output, source in MACOS_INPUTS.items():
        command = [uv, "pip", "compile", str(ROOT / source), "--output-file", str(ROOT / output),
                   "--python-platform", "aarch64-apple-darwin", "--python-version", "3.11", "--generate-hashes",
                   "--no-header", "--quiet"]
        subprocess.run(command, check=True, cwd=ROOT)
        text = (ROOT / output).read_text(encoding="utf-8")
        header = (f"#\n# Compiled for macOS arm64 (CPython 3.11) from {source} by\n"
                  "# scripts/desktop_locks.py compile-macos (uv pip compile). Do not edit.\n#\n")
        (ROOT / output).write_text(header + text, encoding="utf-8")
        print(f"wrote {output}")
    return derive()


def wheelhouse() -> int:
    """Wheels for locked packages that publish only a source archive, built from the archive the lock vouches for."""
    catalog = _catalog()
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    built = 0
    for pack in catalog.runtimes.values():
        if not (ROOT / pack.lock).is_file():
            continue
        lock = read_lock(ROOT / pack.lock)
        _, needs = resolve(lock, pack.platform, wheelhouse=WHEELHOUSE)
        for spec in needs:
            item = lock.get(spec.split("==", 1)[0])
            assert item is not None
            sdist = sdist_for(item)
            if sdist is None:
                print(f"{pack.id}: {spec} has neither a compatible wheel nor a source archive", file=sys.stderr)
                return 1
            with tempfile.TemporaryDirectory() as scratch:
                archive = Path(scratch) / sdist["filename"]
                from app.models.packfiles import _http_get

                archive.write_bytes(_http_get(sdist["url"]))
                import hashlib

                if hashlib.sha256(archive.read_bytes()).hexdigest() not in item.hashes:
                    print(f"{spec}: the source archive does not match the lock", file=sys.stderr)
                    return 1
                subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(WHEELHOUSE),
                                str(archive)], check=True)
            built += 1
            print(f"built {spec}")
    print(f"{built} wheel(s) built")
    return 0


def packfiles() -> int:
    catalog = _catalog()
    failed = False
    for pack in catalog.runtimes.values():
        if not (ROOT / pack.lock).is_file():
            print(f"skip {pack.id}: {pack.lock} does not exist yet")
            continue
        text = (ROOT / pack.lock).read_text(encoding="utf-8")
        files, needs = resolve(parse_lock(text), pack.platform, wheelhouse=WHEELHOUSE)
        if needs:
            failed = True
            print(f"{pack.id}: no wheel for {', '.join(needs)}; run wheelhouse first", file=sys.stderr)
            continue
        write_pack_files(ROOT / pack.files, pack.id, pack.platform, pack.lock, text, files)
        size = sum(item.size or 0 for item in files if item.source == "index") / 1e9
        print(f"wrote {pack.files}: {len(files)} wheels, {size:.2f} GB to download")
    return 1 if failed else 0


def check() -> list[str]:
    catalog = _catalog()
    problems: list[str] = []
    for pack in catalog.runtimes.values():
        lock_path = ROOT / pack.lock
        if not lock_path.is_file():
            problems.append(f"{pack.id}: {pack.lock} is missing")
            continue
        text = lock_path.read_text(encoding="utf-8")
        try:
            lock = parse_lock(text)
        except LockError as exc:
            problems.append(f"{pack.id}: {exc}")
            continue
        if pack.kind == "overlay":
            source = ROOT / pack.source_lock
            if not source.is_file():
                problems.append(f"{pack.id}: source lock {pack.source_lock} is missing")
            else:
                problems += [f"{pack.id}: {item}" for item in check_overlay(lock, read_lock(source))]
        if pack.kind == "torch-layer":
            services = {item.source_lock: read_lock(ROOT / item.source_lock)
                        for item in _overlays_on(catalog, pack.id) if (ROOT / item.source_lock).is_file()}
            problems += [f"{pack.id}: {item}" for item in check_torch_pins(lock, services)]
        files_path = ROOT / pack.files
        if not files_path.is_file():
            problems.append(f"{pack.id}: {pack.files} is missing; run packfiles")
            continue
        try:
            listed = load_pack_files(files_path)
        except (PackFilesError, KeyError, TypeError) as exc:
            problems.append(f"{pack.id}: {exc}")
            continue
        if listed.runtime != pack.id or listed.platform != pack.platform:
            problems.append(f"{pack.id}: {pack.files} is for {listed.runtime} on {listed.platform}")
        problems += check_pack_files(listed, lock, text, wheelhouse=WHEELHOUSE)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["derive", "compile-macos", "wheelhouse", "packfiles", "check"])
    args = parser.parse_args(argv)
    if args.command == "derive":
        return derive()
    if args.command == "compile-macos":
        return compile_macos()
    if args.command == "wheelhouse":
        return wheelhouse()
    if args.command == "packfiles":
        return packfiles()
    problems = check()
    for problem in problems:
        print(problem)
    print("desktop locks: ok" if not problems else f"desktop locks: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
