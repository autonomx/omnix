"""Start a model service in its runtime pack (desktop roadmap §4.2, §4.3).

    python -S -m app.desktop.service_boot stt|tts|image|stt-mlx

The supervisor starts every model service on the bundled interpreter with
``-S``, so the interpreter's own ``site-packages`` (the gateway's packages) is
never added: a package missing from a pack must fail loudly, not load the
gateway's version. This module then adds the pack folders the supervisor names
in ``OMNIX_DESKTOP_SITE_DIRS`` (the service's overlay first, then the shared
Torch layer) with ``site.addsitedir``, so ``.pth`` files inside the packs still
work, and runs the service's usual entry point. Every folder must be inside the
packs folder; anything else is refused.

On macOS the supervisor names itself in ``OMNIX_DESKTOP_PARENT_PID``: when it
dies the service is reparented, notices, and shuts down as on a graceful stop,
so no model stays loaded without an Omnix that owns it. Windows needs no watch:
the supervisor's kill-on-close Job Object ends every child with it. (Not a stdin
pipe: on Windows a read pending on it blocks other uses of the handle, such as a
library starting a subprocess, and the service hung while loading.)
"""
from __future__ import annotations

import os
import runpy
import signal
import site
import sys
import sysconfig
import threading
import time
from pathlib import Path

# After the supervisor is gone: this long for the graceful shutdown, then the process exits regardless.
ORPHAN_GRACE_SECONDS = 20.0
PARENT_POLL_SECONDS = 2.0

ENTRY_MODULES = {
    "stt": "services.stt.parakeet_stt_server",
    "tts": "services.tts.tts_server",
    "stt-mlx": "services.stt.parakeet_mlx_server",
}


class ServiceBootError(RuntimeError):
    pass


def pack_site_dirs(environ: dict[str, str] | os._Environ[str] | None = None) -> list[Path]:
    source = os.environ if environ is None else environ
    packs = (source.get("OMNIX_PACKS_DIR") or "").strip()
    raw = (source.get("OMNIX_DESKTOP_SITE_DIRS") or "").strip()
    if not packs or not raw:
        raise ServiceBootError("OMNIX_PACKS_DIR and OMNIX_DESKTOP_SITE_DIRS name the service's runtime packs")
    root = Path(packs).resolve()
    folders = []
    for item in raw.split(os.pathsep):
        folder = Path(item).resolve()
        if root not in folder.parents:
            raise ServiceBootError(f"{folder} is not inside the packs folder {root}")
        if not folder.is_dir():
            raise ServiceBootError(f"the runtime pack folder {folder} is missing; install it from Settings, Models")
        folders.append(folder)
    return folders


def interpreter_site_packages() -> set[Path]:
    """The bundled interpreter's own package folders, which a service must never import from."""
    found = set()
    for key in ("purelib", "platlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            found.add(Path(value).resolve())
    for value in getattr(site, "getsitepackages", lambda: [])():
        found.add(Path(value).resolve())
    # On Windows getsitepackages() also names the interpreter's own folder, which holds the standard library.
    return {path for path in found if path.name in {"site-packages", "dist-packages"}}


def prepare(folders: list[Path]) -> None:
    """Drop the interpreter's site-packages from sys.path, then add the packs, overlay first."""
    forbidden = interpreter_site_packages()
    sys.path[:] = [entry for entry in sys.path if not entry or Path(entry).resolve() not in forbidden]
    for folder in folders:
        site.addsitedir(str(folder))


def foreign_modules(folders: list[Path], *, app_source: Path) -> list[str]:
    """Modules loaded from outside the standard library, the app source and the packs (should be none)."""
    # Where os.py is, and the base interpreter's DLLs (Windows extension modules); a venv's sysconfig points elsewhere.
    stdlib = {Path(os.__file__).resolve().parent, (Path(sys.base_prefix) / "DLLs").resolve()}
    allowed = [*stdlib, app_source.resolve(), *(folder.resolve() for folder in folders)]
    forbidden = interpreter_site_packages()
    found = []
    for name, module in list(sys.modules.items()):
        location = getattr(module, "__file__", None)
        if not location:
            continue
        path = Path(location).resolve()
        if any(root == path or root in path.parents for root in forbidden) or not any(
                root == path or root in path.parents for root in allowed):
            found.append(f"{name} ({path})")
    return sorted(found)


def _stop_when_orphaned(parent: int, getppid=os.getppid, poll: float = PARENT_POLL_SECONDS) -> threading.Thread:
    """Stops this service gracefully once its supervisor is gone (and for good after a grace period)."""

    def watch() -> None:
        while getppid() == parent:
            time.sleep(poll)
        signal.raise_signal(signal.SIGTERM)
        time.sleep(ORPHAN_GRACE_SECONDS)
        os._exit(1)

    thread = threading.Thread(target=watch, name="omnix-parent-watch", daemon=True)
    thread.start()
    return thread


def run(service: str) -> None:
    folders = pack_site_dirs()
    prepare(folders)
    parent = os.environ.get("OMNIX_DESKTOP_PARENT_PID", "")
    if parent.isdigit() and sys.platform != "win32":
        _stop_when_orphaned(int(parent))
    if service == "image":
        import uvicorn

        from app.config.env import env_int
        from app.runtime.net import bind_host

        port = env_int("OMNIX_IMAGE_PORT", 5301, minimum=1, maximum=65535)
        uvicorn.run("services.image.image_service_app:app", host=bind_host(), port=port)
        return
    module = ENTRY_MODULES.get(service)
    if module is None:
        raise ServiceBootError(f"unknown model service {service!r}")
    sys.argv = [module]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: python -S -m app.desktop.service_boot stt|tts|image|stt-mlx\n")
        return 2
    try:
        run(args[0])
    except ServiceBootError as exc:
        sys.stderr.write(f"[service_boot] {exc}\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
