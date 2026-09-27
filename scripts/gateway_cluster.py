"""Supervise one worker and local API replicas using private stdin shutdown pipes."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time


def wait_for_parent_control() -> None:
    if os.name != 'nt':
        sys.stdin.readline()
        return
    # A blocking CRT stdin read can deadlock Windows native-library loading
    # (including NumPy) in another thread. Inspect the private pipe without
    # holding a CRT read lock; any input or pipe closure requests shutdown.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    peek = ctypes.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                     ctypes.POINTER(wintypes.DWORD)]
    peek.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    while True:
        available = wintypes.DWORD()
        if not peek(handle, None, 0, None, ctypes.byref(available), None) or available.value:
            return
        time.sleep(.2)


def replica_ports(worker_port: int, count: int) -> list[int]:
    if not 0 <= count <= 8 or not 1 <= worker_port <= 65535 - count:
        raise ValueError("Gateway requires a valid worker port and zero to eight API replicas")
    return list(range(worker_port + 1, worker_port + count + 1))


def child_environment(role: str) -> dict[str, str]:
    if role not in {"worker", "api"}:
        raise ValueError("Invalid gateway role")
    env = dict(os.environ, OMNIX_GATEWAY_BACKGROUND_ROLE=role)
    if env.get('OMNIX_TTS_URL'):
        env['OMNIX_GATEWAY_TTS_HTTP'] = '1'
    if role == "api":
        env["OMNIX_TTS_STARTUP_WARMUP"] = "0"
    return env


def stop_children(children, timeout: float = 20) -> None:
    # EOF also requests shutdown if the supervisor exits unexpectedly. No public
    # administrative HTTP endpoint or persisted credential is needed.
    for child in children:
        if child.stdin is not None:
            try:
                child.stdin.write("stop\n")
                child.stdin.flush()
                child.stdin.close()
            except (OSError, ValueError):
                pass
    for child in children:
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)


def serve_cluster(args, count: int) -> int:
    ports = [args.port, *replica_ports(args.port, count)]
    if args.reload:
        raise ValueError("Reload is incompatible with supervised gateway replicas")
    # Never evict an unrelated listener. The launcher owns the old gateway's
    # stop/restart sequence; replica ports must be available before starting.
    for port in ports:
        with socket.socket() as sock:
            sock.bind((args.host, port))
    children = []
    stopping = threading.Event()
    if args.managed_stdin:
        def watch_control():
            wait_for_parent_control()
            stopping.set()
        threading.Thread(target=watch_control, name='gateway-supervisor-control', daemon=True).start()
    previous = {}
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            previous[signum] = signal.signal(signum, lambda *_: stopping.set())
    runner = Path(__file__).with_name("run_omnix_gateway.py")
    try:
        for index, port in enumerate(ports):
            role = "worker" if index == 0 else "api"
            child = subprocess.Popen(
                [sys.executable, str(runner), "--app", args.app, "--host", args.host,
                 "--port", str(port), "--api-replicas", "0", "--managed-stdin"],
                cwd=runner.parent.parent,
                env=child_environment(role),
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            children.append(child)
            print(f"Gateway {role} started: pid={child.pid} port={port}", flush=True)
        while not stopping.wait(.5):
            exited = [(child.pid, child.poll()) for child in children if child.poll() is not None]
            if exited:
                raise RuntimeError(f"Gateway cohort process exited: {exited}")
        return 0
    finally:
        stop_children(children)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def watch_parent_stdin(server) -> None:
    def watch():
        wait_for_parent_control()
        server.should_exit = True

    threading.Thread(target=watch, name="gateway-parent-control", daemon=True).start()
