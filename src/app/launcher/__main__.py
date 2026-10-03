"""``python -m app.launcher start``: check the database, migrate, then serve the launcher (WP-11.4).

The launcher dashboard (port 5055) supervises the services. Once it answers,
the gateway is started; when the gateway is healthy, the web app is started.
``start_all.sh`` is a thin wrapper around this command.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import TextIO

import httpx

LAUNCHER_PORT = 5055
_HEADERS = {"X-Omnix-Client": "launcher"}


def _say(message: str, stream: TextIO | None = None) -> None:
    target = stream or sys.stdout
    target.write(message + "\n")
    target.flush()


def _module(*args: str) -> int:
    return subprocess.run([sys.executable, "-m", *args], check=False).returncode


def start_services(
    launcher_url: str,
    gateway_url: str,
    *,
    timeout_seconds: float,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Start the gateway through the launcher, then the web app once the gateway is healthy."""
    owned = client is None
    client = client or httpx.Client(timeout=10, headers=_HEADERS)
    deadline = time.monotonic() + timeout_seconds
    gateway_requested = False
    try:
        while time.monotonic() < deadline:
            try:
                if not gateway_requested:
                    client.get(f"{launcher_url}/api/services").raise_for_status()
                    client.post(f"{launcher_url}/api/services/gateway/start").raise_for_status()
                    gateway_requested = True
                if client.get(f"{gateway_url}/api/health", timeout=2).status_code == 200:
                    web = client.post(f"{launcher_url}/api/services/web/start")
                    if web.status_code == 200 and web.json().get("ok"):
                        _say("[STARTUP] Omnix gateway and web app are ready.")
                        return True
            except (httpx.HTTPError, ValueError):
                pass
            sleep(1)
        _say("[STARTUP] WARNING: the gateway and web app were not ready before the startup timeout.")
        return False
    finally:
        if owned:
            client.close()


def start(args: argparse.Namespace) -> int:
    if sys.version_info[:2] != (3, 11):
        _say(f"Omnix requires Python 3.11; this is {sys.version.split()[0]} ({sys.executable})", sys.stderr)
        return 1
    for step in (("app.persistence", "health"), ("app.persistence", "migrate")):
        if _module(*step) != 0:
            _say(f"[LAUNCHER] {' '.join(step)} failed; see docs/SETUP.md (PostgreSQL).", sys.stderr)
            return 1
    from app.runtime.net import bind_host

    host = bind_host()
    loopback = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    threading.Thread(
        target=start_services,
        args=(f"http://{loopback}:{LAUNCHER_PORT}", args.gateway_url),
        kwargs={"timeout_seconds": args.startup_timeout},
        name="omnix-launcher-autostart",
        daemon=True,
    ).start()
    import uvicorn

    uvicorn.run("app.launcher.runtime_control_app:app", host=host, port=LAUNCHER_PORT, lifespan="on")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.launcher", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    starting = commands.add_parser("start", help="migrate and run the launcher with the gateway and web app")
    starting.add_argument("--gateway-url", default="http://127.0.0.1:8000")
    starting.add_argument("--startup-timeout", type=float, default=180.0)
    args = parser.parse_args(argv)
    return start(args)


if __name__ == "__main__":
    raise SystemExit(main())
