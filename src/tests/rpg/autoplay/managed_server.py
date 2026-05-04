from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from tests.rpg.autoplay.turn_runtime import probe_live_http_health


def _read_process_pipe(pipe) -> str:
    if pipe is None:
        return ""
    try:
        return pipe.read()[:4000]
    except Exception as exc:
        return f"<failed_to_read_pipe:{type(exc).__name__}:{exc}>"


def start_managed_app_server(
    *,
    base_url: str = "http://127.0.0.1:5000",
    startup_timeout_seconds: int = 60,
) -> Dict[str, Any]:
    """Best-effort app server startup for autoplay.

    Prefer the existing manual harness server management when available. Fall back
    to common local commands.
    """
    health = probe_live_http_health(base_url)
    if health.get("ok"):
        return {
            "ok": True,
            "already_running": True,
            "base_url": base_url,
            "health": health,
        }

    # Reuse manual harness server management if it exists.
    try:
        from tests.rpg.manual.managed_servers import (
            ensure_servers_running,  # type: ignore
        )

        result = ensure_servers_running()
        deadline = time.time() + startup_timeout_seconds
        while time.time() < deadline:
            health = probe_live_http_health(base_url)
            if health.get("ok"):
                return {
                    "ok": True,
                    "started_by": "tests.rpg.manual.managed_servers.ensure_servers_running",
                    "manager_result": result,
                    "base_url": base_url,
                    "health": health,
                }
            time.sleep(1)
        return {
            "ok": False,
            "reason": "managed_server_started_but_health_failed",
            "manager_result": result,
            "base_url": base_url,
            "health": health,
        }
    except Exception as exc:
        manual_error = f"{type(exc).__name__}: {exc}"

    commands = []
    if Path("start_all.bat").exists():
        commands.append(["cmd", "/c", "start_all.bat"])
    if Path("scripts/start_all.bat").exists():
        commands.append(["cmd", "/c", "scripts\\start_all.bat"])
    if Path("src/app/main.py").exists():
        commands.append([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "5000"])
    if Path("src/main.py").exists():
        commands.append([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "5000"])
    commands.extend(
        [
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "5000"],
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "5000"],
        ]
    )
    attempts = []
    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(Path.cwd()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.time() + startup_timeout_seconds
            while time.time() < deadline:
                health = probe_live_http_health(base_url)
                if health.get("ok"):
                    return {
                        "ok": True,
                        "started_by": "subprocess",
                        "command": command,
                        "pid": process.pid,
                        "base_url": base_url,
                        "health": health,
                        "manual_manager_error": manual_error,
                    }
                if process.poll() is not None:
                    break
                time.sleep(1)
            returncode = process.poll()
            attempt = {
                "command": command,
                "pid": process.pid,
                "returncode": returncode,
            }
            if returncode is not None:
                attempt["stdout"] = _read_process_pipe(process.stdout)
                attempt["stderr"] = _read_process_pipe(process.stderr)
            else:
                attempt["stdout"] = "<process_still_running>"
                attempt["stderr"] = "<process_still_running>"
            attempts.append(attempt)
        except Exception as exc:
            attempts.append(
                {
                    "command": command,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return {
        "ok": False,
        "reason": "managed_app_server_unavailable",
        "base_url": base_url,
        "manual_manager_error": manual_error,
        "attempts": attempts,
        "health": probe_live_http_health(base_url),
    }