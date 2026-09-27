#!/usr/bin/env python3
"""
Canonical Omnix FastAPI entrypoint.
This file is named launch.py specifically to avoid module name collision with src/app package.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

# File now lives inside src/, so add this directory directly
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from main import HOST, PORT, app
from app.runtime.net import bind_host


def create_app():
    return app


def _is_port_available(host: str, port: int) -> bool:
    probe_host = bind_host(host)
    family = socket.AF_INET6 if ":" in probe_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, int(port)))
        except OSError:
            return False
    return True


def _launcher_auto_kill_enabled() -> bool:
    return os.environ.get("OMNIX_LAUNCHER_KILL_PORT", "").strip().lower() in {"1", "true", "yes", "on"}


def _find_port_owner_pids(port: int) -> list[int]:
    if os.name != "nt":
        return []

    script = (
        f"Get-NetTCPConnection -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -Unique"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []

    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid() and pid not in pids:
            pids.append(pid)
    return pids


def _kill_processes_for_port(port: int) -> list[int]:
    killed: list[int] = []
    for pid in _find_port_owner_pids(port):
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            continue
        killed.append(pid)
    return killed


def _try_clear_port(host: str, port: int) -> bool:
    if _is_port_available(host, port):
        return True
    if not _launcher_auto_kill_enabled():
        return False

    killed = _kill_processes_for_port(port)
    if killed:
        print(f"[launcher] stopped stale process(es) on port {port}: {', '.join(str(pid) for pid in killed)}")
    return _is_port_available(host, port)


def _print_port_conflict_help(host: str, port: int) -> None:
    print("\n" + "=" * 50)
    print("Omnix FastAPI Server could not start")
    print("=" * 50)
    print(f"Port already in use: {host}:{port}")
    print("Another Omnix/server process is already bound to this port.")
    print("\nFind the process using PowerShell:")
    print(f"  Get-NetTCPConnection -LocalPort {port} | Select-Object LocalAddress,LocalPort,State,OwningProcess")
    print("\nThen stop it, or kill the owning process:")
    print("  Stop-Process -Id <OwningProcess> -Force")
    if os.name == "nt":
        print("\nOr allow the Omnix launcher to clear stale port owners automatically:")
        print("  $env:OMNIX_LAUNCHER_KILL_PORT = '1'")
        print("  python src\\launch.py")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    if not _try_clear_port(HOST, PORT):
        _print_port_conflict_help(HOST, PORT)
        raise SystemExit(1)

    from app.security.service_credentials import initialize_service_token
    initialize_service_token()

    print("\n" + "=" * 50)
    print("Omnix Web Gateway")
    print("=" * 50)
    print(f"Gateway: http://{HOST}:{PORT}")
    print(f"API docs: http://{HOST}:{PORT}/docs")
    print("=" * 50 + "\n")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
