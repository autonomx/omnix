#!/usr/bin/env python3
"""
Canonical Omnix FastAPI entrypoint.
This file is named launch.py specifically to avoid module name collision with src/app package.
"""

import socket
import sys
from pathlib import Path

# File now lives inside src/, so add this directory directly
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from run_app import HOST, PORT, app


def create_app():
    return app


def _is_port_available(host: str, port: int) -> bool:
    probe_host = "0.0.0.0" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, int(port)))
        except OSError:
            return False
    return True


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
    print("=" * 50 + "\n")


if __name__ == "__main__":
    if not _is_port_available(HOST, PORT):
        _print_port_conflict_help(HOST, PORT)
        raise SystemExit(1)

    print("\n" + "=" * 50)
    print("Omnix FastAPI Server - Ultra Low Latency")
    print("=" * 50)
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/conversation")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/tts")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/audiobook")
    print("=" * 50 + "\n")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
