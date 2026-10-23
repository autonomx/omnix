"""Install, check and remove desktop runtime and model packs from the command line (desktop roadmap §4.3, DT-0.1).

    python scripts/desktop_packs.py --packs DIR status
    python scripts/desktop_packs.py --packs DIR install bundle voice-output [--link-from ~/.cache/huggingface/hub]
    python scripts/desktop_packs.py --packs DIR install runtime torch-windows-x64
    python scripts/desktop_packs.py --packs DIR install model qwen3-tts-0.6b-base
    python scripts/desktop_packs.py --packs DIR verify runtime tts-windows-x64
    python scripts/desktop_packs.py --packs DIR remove runtime tts-windows-x64

The same stores the desktop app's install jobs use, without the app: for maintainers checking a release's packs
and for the shared-Torch spike. ``--link-from`` hard-links model files from an existing Hugging Face cache when
their digest matches the catalog (same drive only) instead of downloading them again; every file is still checked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.models import catalog as model_catalog  # noqa: E402
from app.models.packs import ModelStore, PackError, RuntimeStore  # noqa: E402


def _progress() -> object:
    last = [0.0]

    def report(done: int, total: int, message: str) -> None:
        now = time.monotonic()
        if now - last[0] < 2.0 and done < total:
            return
        last[0] = now
        share = f"{100 * done / total:5.1f}%" if total else ""
        print(f"  {message}: {done / 1e9:.2f} / {total / 1e9:.2f} GB {share}", flush=True)

    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def linking_fetch(source: Path, catalog: model_catalog.Catalog):
    """A fetch for ModelStore.install that hard-links a matching file from another cache before downloading."""
    from app.models.downloads import _hub_fetch

    def fetch(*, repo_id: str, filename: str, revision: str, cache_dir: str, **kwargs) -> str:
        repo = source / ("models--" + repo_id.replace("/", "--"))
        expected = {item.path: item.sha256 for entry in catalog.models.values() if entry.repo == repo_id
                    for item in entry.files}.get(filename)
        target = Path(cache_dir) / ("models--" + repo_id.replace("/", "--")) / "snapshots" / revision / filename
        for candidate in sorted(repo.glob(f"snapshots/*/{filename}")):
            try:
                if expected and _sha256(candidate.resolve()) == expected:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.unlink(missing_ok=True)
                    os.link(candidate.resolve(), target)
                    print(f"  linked {repo_id}/{filename}", flush=True)
                    return str(target)
            except OSError:
                continue
        return _hub_fetch(repo_id=repo_id, filename=filename, revision=revision, cache_dir=cache_dir, **kwargs)

    return fetch


def _bundle_parts(catalog: model_catalog.Catalog, bundle_id: str) -> tuple[list[str], list[str]]:
    variant = catalog.bundle(bundle_id).variant(model_catalog.current_platform())
    if variant is None:
        raise PackError(f"{bundle_id} is not available on this platform")
    return list(variant.models), [pack.id for pack in catalog.runtime_closure(variant.runtimes)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packs", required=True, type=Path)
    parser.add_argument("--link-from", type=Path, help="an existing Hugging Face hub cache to hard-link models from")
    parser.add_argument("command", choices=["status", "install", "verify", "remove"])
    parser.add_argument("kind", nargs="?", choices=["bundle", "runtime", "model"])
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args(argv)
    catalog = model_catalog.load()
    runtimes = RuntimeStore(args.packs, catalog)
    models = ModelStore(args.packs / "models", catalog)
    platform = model_catalog.current_platform()
    if args.command == "status":
        report = {
            "runtimes": {pack.id: runtimes.status(pack.id) for pack in catalog.runtimes.values() if pack.platform == platform},
            "models": {entry.id: models.installed(entry.id) for entry in catalog.models.values() if entry.pinned},
        }
        print(json.dumps(report, indent=1))
        return 0
    if not args.kind or not args.ids:
        parser.error("name what to act on: bundle|runtime|model and its ids")
    runtime_ids: list[str] = []
    model_ids: list[str] = []
    for item in args.ids:
        if args.kind == "bundle":
            bundle_models, bundle_runtimes = _bundle_parts(catalog, item)
            model_ids += bundle_models
            runtime_ids += [runtime for runtime in bundle_runtimes if runtime not in runtime_ids]
        elif args.kind == "runtime":
            runtime_ids += [pack.id for pack in catalog.runtime_closure([item]) if pack.id not in runtime_ids] \
                if args.command == "install" else [item]
        else:
            model_ids.append(item)
    try:
        if args.command == "install":
            for runtime_id in runtime_ids:
                started = time.monotonic()
                print(f"runtime {runtime_id}", flush=True)
                runtimes.install(runtime_id, progress=_progress())
                print(f"  installed in {time.monotonic() - started:.0f} s", flush=True)
            fetch = linking_fetch(args.link_from, catalog) if args.link_from else None
            for model_id in model_ids:
                print(f"model {model_id}", flush=True)
                models.install(model_id, progress=_progress(), fetch=fetch)
            return 0
        if args.command == "verify":
            failed = False
            for runtime_id in runtime_ids:
                problems = runtimes.verify(runtime_id)
                failed = failed or bool(problems)
                print(f"runtime {runtime_id}: " + ("ok" if not problems else "; ".join(problems[:10])))
            for model_id in model_ids:
                problems = models.verify(model_id)
                failed = failed or bool(problems)
                print(f"model {model_id}: " + ("ok" if not problems else "; ".join(problems[:10])))
            return 1 if failed else 0
        for model_id in model_ids:
            models.remove(model_id)
        for runtime_id in reversed(runtime_ids):
            runtimes.remove(runtime_id)
        return 0
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
