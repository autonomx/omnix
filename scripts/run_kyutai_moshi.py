from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

_STOP_REQUESTED = threading.Event()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _request_stop(_signum: int, _frame: object) -> None:
    _STOP_REQUESTED.set()


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signal.signal(sigbreak, _request_stop)


def _compose_command(root: Path) -> list[str]:
    unmute_dir = Path(
        os.environ.get("KYUTAI_UNMUTE_DIR", str(root.parent / "unmute"))
    ).expanduser()
    upstream_compose = unmute_dir / "docker-compose.yml"
    omnix_override = Path(
        os.environ.get(
            "KYUTAI_OMNIX_COMPOSE_FILE",
            str(root / "docker-compose.kyutai-stt.yml"),
        )
    ).expanduser()

    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI was not found. Start or install Docker Desktop first.")
    if not upstream_compose.is_file():
        raise RuntimeError(
            "Pinned Unmute checkout was not found. "
            f"Expected {upstream_compose}. Set KYUTAI_UNMUTE_DIR to the checkout path."
        )
    if not omnix_override.is_file():
        raise RuntimeError(f"Omnix Kyutai compose override was not found: {omnix_override}")

    return [
        "docker",
        "compose",
        "-f",
        str(upstream_compose),
        "-f",
        str(omnix_override),
    ]


def _stop_service(base_command: list[str]) -> None:
    print("[KYUTAI MOSHI] Stopping Docker Compose service stt...", flush=True)
    try:
        subprocess.run(
            [*base_command, "stop", "stt"],
            check=False,
            timeout=30,
        )
    except Exception as exc:
        print(
            f"[KYUTAI MOSHI] Could not stop stt cleanly: {type(exc).__name__}: {exc}",
            flush=True,
        )


def main() -> int:
    root = _repo_root()
    try:
        base_command = _compose_command(root)
    except RuntimeError as exc:
        print(f"[KYUTAI MOSHI] ERROR: {exc}", flush=True)
        return 2

    _install_signal_handlers()
    command = [*base_command, "up", "--build", "stt"]
    print("[KYUTAI MOSHI] Starting: " + " ".join(command), flush=True)
    process = subprocess.Popen(command, cwd=str(root))

    try:
        while process.poll() is None and not _STOP_REQUESTED.wait(0.25):
            pass
        if _STOP_REQUESTED.is_set() and process.poll() is None:
            _stop_service(base_command)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        if _STOP_REQUESTED.is_set():
            _stop_service(base_command)

    return int(process.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
