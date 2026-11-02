"""Whether the TTS service can bind its port, clearing a stale owner on Windows when allowed."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from typing import List

from app.config.env import env_bool, env_str
from app.runtime.net import bind_host

logger = logging.getLogger(__name__)


def _normalize_bind_host(host: str) -> str:
    return bind_host(str(host or "").strip() or None)


def _can_bind_port(host: str, port: int) -> bool:
    bind_host = _normalize_bind_host(host)
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, int(port)))
        except OSError:
            return False
    return True


def _wait_for_port_release(host: str, port: int, timeout_s: float = 8.0, interval_s: float = 0.25) -> bool:
    """Wait briefly for Windows to release a port after Stop-Process."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        if _can_bind_port(host, port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.05, float(interval_s)))


def _windows_port_owner_pids(port: int) -> List[int]:
    if os.name != "nt":
        return []
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-NetTCPConnection -LocalPort "
        + str(int(port))
        + " -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    pids: List[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def _kill_windows_port_owners(port: int) -> List[int]:
    killed: List[int] = []
    for pid in _windows_port_owner_pids(port):
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            killed.append(pid)
        except Exception:
            logger.debug("suppressed error in %s", "_kill_windows_port_owners", exc_info=True)
            continue
    return killed


def _preflight_tts_port(host: str, port: int) -> bool:
    if _can_bind_port(host, port):
        return True

    should_kill = env_bool("OMNIX_LAUNCHER_KILL_PORT", False)
    if should_kill and os.name == "nt":
        killed = _kill_windows_port_owners(port)
        if killed:
            print(f"[TTS SERVER] stopped stale process(es) on port {port}: {', '.join(map(str, killed))}")
        wait_timeout_s = float(env_str("OMNIX_LAUNCHER_PORT_RELEASE_TIMEOUT", "8") or 8)
        if _wait_for_port_release(host, port, timeout_s=wait_timeout_s):
            return True
        remaining = _windows_port_owner_pids(port)
        if remaining:
            print(f"[TTS SERVER] port {port} still owned after cleanup: {', '.join(map(str, remaining))}")
        elif killed:
            print(f"[TTS SERVER] port {port} did not become bindable within {wait_timeout_s:.1f}s after cleanup")

    print("\n" + "=" * 50)
    print("Omnix TTS Server could not start")
    print("=" * 50)
    print(f"Port already in use: {host}:{port}")
    print("Another TTS/server process is already bound to this port.")
    print("")
    print("Find the process using PowerShell:")
    print(f"  Get-NetTCPConnection -LocalPort {port} | Select-Object LocalAddress,LocalPort,State,OwningProcess")
    print("")
    print("Then stop it, or kill the owning process:")
    print("  Stop-Process -Id <OwningProcess> -Force")
    print("")
    print("Or allow Omnix to clean stale port owners before launch:")
    print("  $env:OMNIX_LAUNCHER_KILL_PORT = '1'")
    print("=" * 50)
    return False
