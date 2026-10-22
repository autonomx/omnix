"""Stage the runtime the desktop app ships (desktop roadmap DT-3.1), adapted from MarketPulse's build/stage.py.

    python desktop/staging/stage.py all [--platform windows-x64|macos-arm64]
    python desktop/staging/stage.py python     # CPython 3.11 + requirements/gateway.lock.txt, isolated import roots
    python desktop/staging/stage.py postgres   # PostgreSQL 17 bin, lib, share (no pgAdmin, docs, headers, symbols)
    python desktop/staging/stage.py ffmpeg     # the pinned LGPL ffmpeg (Windows)
    python desktop/staging/stage.py prune      # drop what the running app never loads (debug symbols, pip, Tk, tests)
    python desktop/staging/stage.py app        # the backend source, from git's file list only
    python desktop/staging/stage.py web        # the built web app (run `npm --prefix web run build` first)
    python desktop/staging/stage.py check      # import check in the staged interpreter, path lengths, sizes

The platform defaults to the machine's: a platform's Python installs its own dependencies, so the macOS runtime is
staged on a Mac. desktop/staging/stage/ becomes the installed app's resources folder (``runtime``):

    python/    CPython; Windows: python311._pth lists ../app/src and ../app/scripts (PYTHON* variables ignored);
               macOS: site-packages/omnix-desktop.pth adds the same roots
    postgres/  PostgreSQL binaries
    ffmpeg/    ffmpeg (Windows) and its licence
    app/       src/app, src/services, the gateway scripts, the desktop locks, pack file lists and wheelhouse,
               the tracked resources/ files, and deploy/docker/agent-sandbox.Dockerfile (agent_runtime/sandbox.py
               finds it at that relative path)
    web/dist/  the web build
    licenses/  third-party licence texts
    build-info.json  the commit and pinned versions

No GPU runtime and no model is staged: the setup screen downloads them (roadmap D-2). Every downloaded archive is
checked against pins.json before it is used; nothing is fetched unpinned. The app's files come from ``git ls-files``,
so a stray or untracked file never reaches the installer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "cache"
STAGE = HERE / "stage"
PINS = json.loads((HERE / "pins.json").read_text(encoding="utf-8"))
WINDOWS_PTH = """python311.zip
.
DLLs
Lib
Lib/site-packages
../app/src
../app/scripts
import site
"""
# Relative to python/lib/python3.11/site-packages.
MACOS_PTH = "../../../../app/src\n../../../../app/scripts\n"
POSTGRES_KEEP = ("bin", "lib", "share", "server_license.txt", "commandlinetools_3rd_party_licenses.txt")
# What the app ships from the repository: git's tracked files under these, minus tests.
APP_TREES = ("src/app/", "src/services/", "requirements/desktop/", "resources/")
APP_FILES = ("scripts/run_omnix_gateway.py", "scripts/gateway_cluster.py", "deploy/docker/agent-sandbox.Dockerfile")
# The longest path below the stage a Windows install may hold (NSIS cannot remove paths over 260 characters; the
# installer caps the install folder so that folder + \resources\runtime\ + this stays under it).
MAX_RELATIVE_PATH = 140
PRUNE_PYTHON = (
    "**/*.pdb",  # debug symbols
    "tcl", "DLLs/_tkinter.pyd", "DLLs/tcl86t.dll", "DLLs/tk86t.dll", "Lib/tkinter", "Lib/idlelib", "Lib/turtledemo",
    "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/python3.11/tkinter", "lib/python3.11/idlelib",
    "lib/python3.11/turtledemo", "lib/python3.11/lib-dynload/_tkinter*",
    # The installer's tools: the gateway's dependencies are installed at staging, and packs never use pip.
    "*/site-packages/pip", "*/site-packages/pip-*.dist-info", "*/site-packages/setuptools",
    "*/site-packages/setuptools-*.dist-info", "*/site-packages/_distutils_hack", "*/site-packages/distutils-precedence.pth",
    "lib/python3.11/site-packages/pip", "lib/python3.11/site-packages/pip-*.dist-info",
    "lib/python3.11/site-packages/setuptools", "lib/python3.11/site-packages/setuptools-*.dist-info",
    "lib/python3.11/site-packages/_distutils_hack", "lib/python3.11/site-packages/distutils-precedence.pth",
    # Third-party packages' own test suites.
    "**/site-packages/*/tests", "**/site-packages/*/*/tests", "**/site-packages/*/*/*/tests",
)
PRUNE_POSTGRES = (
    "bin/stackbuilder*", "bin/wx*", "bin/ecpg*", "bin/libecpg*", "bin/libpgtypes*", "bin/pgbench*", "bin/pg_test_*",
    "bin/test_*", "bin/testplug*", "bin/*.lib", "lib/*.lib", "lib/*.a", "share/locale",
)


class StageError(RuntimeError):
    pass


def host_platform() -> str:
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "macos-arm64"
    raise StageError(f"the desktop app is not built for {sys.platform} {platform.machine()}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(family: str, target_platform: str) -> Path:
    """The pinned archive for a platform from the cache, downloading it once; refused if its SHA-256 differs."""
    pin = PINS[family]["platforms"][target_platform]
    url = (pin.get("url") or PINS[family]["url"]).format(asset=pin["asset"])
    target = CACHE / family / pin["asset"]
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        partial = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=600) as response, partial.open("wb") as stream:  # noqa: S310
            shutil.copyfileobj(response, stream)
        partial.replace(target)
    actual = sha256_file(target)
    if actual != pin["sha256"]:
        raise StageError(f"{target.name}: SHA-256 {actual} does not match the pin {pin['sha256']}")
    return target


def _reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _inside(base: Path, target: Path) -> bool:
    return target.resolve().is_relative_to(base.resolve())


def _safe_extract_tar(archive: Path, destination: Path, strip: str) -> None:
    """Extracts members under ``strip/``; symlinks only when they stay inside the destination."""
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.name.startswith(strip + "/"):
                continue
            relative = member.name[len(strip) + 1:]
            target = destination / relative
            if not _inside(destination, target) or member.islnk():
                raise StageError(f"unsafe archive member {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                if not _inside(destination, target.parent / member.linkname):
                    raise StageError(f"symlink leaves the stage: {member.name} -> {member.linkname}")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(member.linkname, target)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open("wb") as out:  # type: ignore[union-attr]
                    shutil.copyfileobj(source, out)
                if member.mode & 0o111:
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def compile_bytecode(target_platform: str, folder: Path, *, skip: str | None = None) -> None:
    """Ships ``folder``'s bytecode, compiled by the staged interpreter: model services never write bytecode (they run
    with PYTHONDONTWRITEBYTECODE, and on macOS the install folder is a signed bundle), so what they import must be
    compiled already. Unchecked-hash bytecode stays valid whatever timestamps the installer gives the files."""
    interpreter, _, _ = python_paths(target_platform)
    command = [str(interpreter), "-I", "-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash"]
    if skip:
        command += ["-x", skip]
    subprocess.run([*command, str(folder)], check=True)


def python_paths(target_platform: str) -> tuple[Path, Path, Path]:
    """(interpreter, site-packages, import-roots file) of the staged Python."""
    python_dir = STAGE / "python"
    if target_platform == "windows-x64":
        return python_dir / "python.exe", python_dir / "Lib" / "site-packages", python_dir / "python311._pth"
    site = python_dir / "lib" / "python3.11" / "site-packages"
    return python_dir / "bin" / "python3", site, site / "omnix-desktop.pth"


def stage_python(target_platform: str) -> None:
    if target_platform != host_platform():
        raise StageError(f"stage the {target_platform} Python on that platform (its interpreter installs the lock)")
    archive = fetch("python", target_platform)
    _reset(STAGE / "python")
    _safe_extract_tar(archive, STAGE / "python", "python")
    interpreter, _, roots = python_paths(target_platform)
    if not interpreter.exists():
        raise StageError(f"{interpreter.name} missing after extraction")
    lock = ROOT / "requirements" / "gateway.lock.txt"
    print(f"installing {lock.relative_to(ROOT)} into the staged interpreter")
    subprocess.run([str(interpreter), "-m", "pip", "install", "--require-hashes", "--no-deps", "--no-warn-script-location",
                    "--disable-pip-version-check", "--no-cache-dir", "-r", str(lock)], check=True)
    # Written last: on Windows a ._pth file isolates the interpreter, which changes pip's own imports.
    roots.write_text(WINDOWS_PTH if target_platform == "windows-x64" else MACOS_PTH, encoding="utf-8", newline="\n")
    # The standard library the model services import; the gateway's site-packages compile on its own first run.
    stdlib = interpreter.parent / "Lib" if target_platform == "windows-x64" else interpreter.parent.parent / "lib" / "python3.11"
    compile_bytecode(target_platform, stdlib, skip="site-packages")
    print(f"python staged: {PINS['python']['version']} ({target_platform})")


def stage_postgres(target_platform: str) -> None:
    archive = fetch("postgres", target_platform)
    postgres_dir = STAGE / "postgres"
    _reset(postgres_dir)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            name = member.filename.replace("\\", "/")
            if not name.startswith("pgsql/"):
                continue
            relative = name[len("pgsql/"):]
            if not relative or relative.split("/", 1)[0] not in POSTGRES_KEEP:
                continue
            target = postgres_dir / relative
            if not _inside(postgres_dir, target):
                raise StageError(f"unsafe archive member {name}")
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = zipped.read(member).decode("utf-8")
                if not _inside(postgres_dir, target.parent / link):
                    raise StageError(f"symlink leaves the stage: {name} -> {link}")
                if sys.platform != "win32":
                    os.symlink(link, target)
                elif (target.parent / link).exists():
                    shutil.copyfile(target.parent / link, target)
                continue
            with zipped.open(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            if mode & 0o111:
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    licenses = STAGE / "licenses" / "postgresql"
    licenses.mkdir(parents=True, exist_ok=True)
    for name in ("server_license.txt", "commandlinetools_3rd_party_licenses.txt"):
        if (postgres_dir / name).is_file():
            shutil.copy2(postgres_dir / name, licenses / name)
    print(f"postgres staged: {PINS['postgres']['version']} ({target_platform})")


def stage_ffmpeg(target_platform: str) -> None:
    """ffmpeg.exe and its licence: STT upload decoding, transcription, exports and dubbing need it (roadmap §4.1)."""
    target = STAGE / "ffmpeg"
    if target_platform not in PINS["ffmpeg"]["platforms"]:
        print(f"no ffmpeg is pinned for {target_platform}; the app uses one on PATH")
        return
    archive = fetch("ffmpeg", target_platform)
    _reset(target)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            parts = member.filename.split("/")
            if len(parts) == 3 and parts[1] == "bin" and parts[2] == "ffmpeg.exe":
                (target / "ffmpeg.exe").write_bytes(zipped.read(member))
            elif len(parts) == 2 and parts[1] == "LICENSE.txt":
                licenses = STAGE / "licenses" / "ffmpeg"
                licenses.mkdir(parents=True, exist_ok=True)
                (licenses / "LICENSE.txt").write_bytes(zipped.read(member))
    if not (target / "ffmpeg.exe").is_file():
        raise StageError("the ffmpeg archive has no bin/ffmpeg.exe")
    (STAGE / "licenses" / "ffmpeg").mkdir(parents=True, exist_ok=True)
    (STAGE / "licenses" / "ffmpeg" / "SOURCE.txt").write_text(
        f"ffmpeg {PINS['ffmpeg']['version']} is bundled under the LGPL (an LGPL build from BtbN FFmpeg-Builds, "
        f"{PINS['ffmpeg']['platforms'][target_platform]['asset']}). Its source is at https://ffmpeg.org and "
        "https://github.com/BtbN/FFmpeg-Builds.\n", encoding="utf-8")
    print(f"ffmpeg staged: {PINS['ffmpeg']['version']}")


def _remove(root: Path, patterns: tuple[str, ...]) -> int:
    freed = 0
    for pattern in patterns:
        for path in sorted(root.glob(pattern), key=lambda found: len(found.parts), reverse=True):
            if not path.exists() and not path.is_symlink():
                continue
            if path.is_dir() and not path.is_symlink():
                freed += sum(child.stat().st_size for child in path.rglob("*") if child.is_file() and not child.is_symlink())
                shutil.rmtree(path)
            else:
                freed += path.lstat().st_size
                path.unlink()
    return freed


def prune(_target_platform: str) -> None:
    python_freed = _remove(STAGE / "python", PRUNE_PYTHON) if (STAGE / "python").is_dir() else 0
    postgres_freed = _remove(STAGE / "postgres", PRUNE_POSTGRES) if (STAGE / "postgres").is_dir() else 0
    print(f"pruned {python_freed / 2**20:.0f} MB from python, {postgres_freed / 2**20:.0f} MB from postgres")


def _test_file(relative: str) -> bool:
    parts = relative.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_") or parts[-1] == "conftest.py"


def _not_distributed(relative: str) -> bool:
    """Tracked files a public installer must not carry.

    The voice-clone reference samples in resources/voice_clones include recordings of real people and of game
    characters, with no record of consent or licence; an installer ships only the default reference voice (and its
    index entry, written by ``stage_app``)."""
    if relative.startswith("resources/voice_clones/"):
        return relative != "resources/voice_clones/default_ref.wav"
    return False


def tracked_app_files() -> list[str]:
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *APP_TREES, *APP_FILES],
                            capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    files = sorted(path for path in listed if path and not _test_file(path) and not _not_distributed(path))
    missing = [path for path in APP_FILES if path not in files]
    if missing:
        raise StageError(f"not tracked by git: {', '.join(missing)}")
    return files


def stage_app(target_platform: str) -> None:
    app_dir = STAGE / "app"
    _reset(app_dir)
    for relative in tracked_app_files():
        source = ROOT / relative
        if not source.is_file():
            raise StageError(f"{relative} is tracked but missing from the working tree")
        (app_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, app_dir / relative)
    compile_bytecode(target_platform, app_dir / "src")
    index = ROOT / "resources" / "voice_clones" / "voice_clones.json"
    if index.is_file():
        voices = json.loads(index.read_text(encoding="utf-8"))
        kept = {name: entry for name, entry in voices.items() if name == "default_ref"}
        target = app_dir / "resources" / "voice_clones" / "voice_clones.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    licenses = STAGE / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, licenses / name)
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *APP_TREES, *APP_FILES],
                                capture_output=True, text=True).stdout.strip())
    (STAGE / "build-info.json").write_text(json.dumps({
        "platform": target_platform, "omnix_commit": commit or None, "uncommitted_changes": dirty,
        "python": PINS["python"]["version"], "postgres": PINS["postgres"]["version"],
        "ffmpeg": PINS["ffmpeg"]["version"] if target_platform in PINS["ffmpeg"]["platforms"] else None,
    }, indent=2) + "\n", encoding="utf-8")
    print("app staged")


def stage_web(_target_platform: str) -> None:
    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").is_file():
        raise StageError("web/dist is missing: run `npm --prefix web run build` first")
    target = STAGE / "web" / "dist"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(dist, target)
    print("web staged")


def _size(path: Path) -> int:
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file() and not child.is_symlink())


def check(target_platform: str) -> None:
    interpreter, _, _ = python_paths(target_platform)
    # The app's and the standard library's bytecode ship too, so their paths count; site-packages' does not ship.
    shipped = (path for path in STAGE.rglob("*")
               if not ("__pycache__" in path.parts and "site-packages" in path.parts))
    longest = max(shipped, key=lambda path: len(str(path.relative_to(STAGE))))
    if len(str(longest.relative_to(STAGE))) > MAX_RELATIVE_PATH:
        raise StageError(f"{longest.relative_to(STAGE)} is longer than {MAX_RELATIVE_PATH} characters")
    script = (
        "import sys, app, gateway_cluster, psycopg, uvicorn, app.desktop.supervise, app.desktop.desktop_app;"
        "from app.models import catalog; catalog.load();"
        "import importlib.util as u; assert u.find_spec('torch') is None, 'torch must not be in the base runtime';"
        "print('imports ok', sys.version.split()[0])"
    )
    env = {"OMNIX_DESKTOP_WEB_DIST": str(STAGE / "web" / "dist"), "PYTHONPATH": str(Path("/nowhere"))}
    if sys.platform == "win32":
        env["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
    subprocess.run([str(interpreter), "-c", script], check=True, cwd=str(STAGE), env=env)
    sizes = {name: round(_size(STAGE / name) / 2**20) for name in ("python", "postgres", "ffmpeg", "app", "web")
             if (STAGE / name).is_dir()}
    sizes["total"] = round(_size(STAGE) / 2**20)
    (STAGE / "size-report.json").write_text(json.dumps({"mib": sizes}, indent=2) + "\n", encoding="utf-8")
    print("sizes (MiB):", json.dumps(sizes))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("part", choices=["all", "python", "postgres", "ffmpeg", "prune", "app", "web", "check"])
    parser.add_argument("--platform", choices=["windows-x64", "macos-arm64"], default=None)
    args = parser.parse_args(argv)
    steps = {"python": stage_python, "postgres": stage_postgres, "ffmpeg": stage_ffmpeg, "prune": prune,
             "app": stage_app, "web": stage_web, "check": check}
    try:
        target_platform = args.platform or host_platform()
        order = ["postgres", "ffmpeg", "python", "prune", "app", "web", "check"]
        for name in (order if args.part == "all" else [args.part]):
            steps[name](target_platform)
    except (StageError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
