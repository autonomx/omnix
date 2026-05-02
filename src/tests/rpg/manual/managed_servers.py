from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Dict, List


def _split_env_list(value: str) -> List[str]:
    value = (value or "").strip()
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


@dataclass
class ManagedServer:
    name: str
    command: str
    cwd: str
    health_url: str = ""
    startup_timeout_seconds: float = 30.0
    env: Dict[str, str] | None = None
    process: subprocess.Popen | None = None

    def start(self) -> None:
        if not self.command:
            return

        env = os.environ.copy()
        if self.env:
            env.update(self.env)

        kwargs = {
            "cwd": self.cwd or None,
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
        }

        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            cmd = self.command
            shell = True
        else:
            cmd = shlex.split(self.command)
            shell = False

        self.process = subprocess.Popen(cmd, shell=shell, **kwargs)  # type: ignore[call-overload]

        if self.health_url:
            self.wait_for_health()

    def wait_for_health(self) -> None:
        if not self.health_url:
            return

        deadline = time.time() + float(self.startup_timeout_seconds or 30.0)
        last_error = ""

        while time.time() < deadline:
            if self.process and self.process.poll() is not None:
                raise RuntimeError(
                    f"managed_server_exited:{self.name}:returncode={self.process.returncode}"
                )

            try:
                with urllib.request.urlopen(self.health_url, timeout=2.0) as response:
                    if 200 <= int(response.status) < 500:
                        return
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            time.sleep(0.5)

        raise RuntimeError(f"managed_server_health_timeout:{self.name}:{last_error}")

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is not None:
            return

        try:
            if sys.platform.startswith("win"):
                process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                process.terminate()
            process.wait(timeout=8)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


class ManagedServerGroup:
    def __init__(self, servers: List[ManagedServer] | None = None) -> None:
        self.servers = list(servers or [])

    @classmethod
    def from_env(cls) -> "ManagedServerGroup":
        names = _split_env_list(os.environ.get("MANUAL_RPG_MANAGED_SERVER_NAMES", ""))
        if not names:
            return cls([])

        servers: List[ManagedServer] = []
        for name in names:
            key = name.upper().replace("-", "_")
            command = os.environ.get(f"MANUAL_RPG_SERVER_{key}_COMMAND", "")
            cwd = os.environ.get(f"MANUAL_RPG_SERVER_{key}_CWD", os.getcwd())
            health_url = os.environ.get(f"MANUAL_RPG_SERVER_{key}_HEALTH_URL", "")
            timeout_raw = os.environ.get(f"MANUAL_RPG_SERVER_{key}_STARTUP_TIMEOUT", "30")
            try:
                timeout = float(timeout_raw)
            except Exception:
                timeout = 30.0

            if not command:
                continue

            servers.append(
                ManagedServer(
                    name=name,
                    command=command,
                    cwd=cwd,
                    health_url=health_url,
                    startup_timeout_seconds=timeout,
                )
            )

        return cls(servers)

    @classmethod
    def from_args(cls, args) -> "ManagedServerGroup":
        if not getattr(args, "manage_servers", False):
            return cls.from_env()

        commands = list(getattr(args, "server_command", []) or [])
        health_urls = list(getattr(args, "managed_server_health_url", []) or [])
        timeout = float(getattr(args, "server_startup_timeout", 90.0) or 90.0)

        servers: List[ManagedServer] = []
        for idx, command in enumerate(commands):
            health_url = health_urls[idx] if idx < len(health_urls) else ""
            servers.append(
                ManagedServer(
                    name=f"server_{idx + 1}",
                    command=command,
                    cwd=os.getcwd(),
                    health_url=health_url,
                    startup_timeout_seconds=timeout,
                )
            )

        return cls(servers)

    def start(self) -> None:
        for server in self.servers:
            server.start()

    def stop(self) -> None:
        for server in reversed(self.servers):
            server.stop()

    def __enter__(self) -> "ManagedServerGroup":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()