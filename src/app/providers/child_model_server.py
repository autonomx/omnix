"""A model server run as a child process of the Omnix process that owns TTS.

Engines whose dependencies cannot share the TTS environment (OmniVoice needs
transformers 5) run in their own environment as a loopback-only child server.
Starting the engine launches the server and waits for its model; stopping it
ends the process, which releases all of its GPU memory, so the swap controller
can swap such an engine like any other.

Each launch generates a token the server requires on every request but
``/health``. A server left by an earlier owner (its pid file survives) is ended
on stop. Fish S2 Pro predates this class and keeps its own lifecycle in
``fish_s2_pro_provider``.
"""
from __future__ import annotations

import logging
import os
import secrets
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.env import environment_copy

logger = logging.getLogger(__name__)


def stop_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30, check=False)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            logger.debug("process %s already gone", pid)


@dataclass
class ManagedChildServer:
    label: str
    port: int
    command: Callable[[], list[str]]
    cwd: Path
    log_path: Path
    pid_path: Path
    startup_timeout_s: float = 600.0
    health_path: str = "/health"
    process: subprocess.Popen[Any] | None = None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    # Extra environment for the child (the desktop app names its runtime packs); it may keep PYTHONPATH.
    environment: Callable[[], dict[str, str]] | None = None
    _http_client: Any = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{int(self.port)}"

    def http(self) -> Any:
        if self._http_client is None:
            import httpx

            self._http_client = httpx.Client(timeout=600.0, headers={"X-Omnix-Child-Token": self.token})
        return self._http_client

    def healthy(self) -> bool:
        """The server answers and reports its model loaded."""
        try:
            response = self.http().get(self.base_url + self.health_path, timeout=3)
        except Exception:
            return False
        if response.status_code != 200:
            return False
        try:
            return bool(response.json().get("ok", True))
        except ValueError:
            return True

    def log_tail(self, lines: int = 12) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(line for line in text.splitlines()[-lines:] if line.strip())

    def launch_and_wait(self) -> None:
        # A server from an earlier owner holds the port with a token we do not know.
        self.terminate()
        self.token = secrets.token_urlsafe(32)
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        env = environment_copy()
        env.pop("PYTHONPATH", None)  # the child must not import Omnix's packages ahead of its own
        if self.environment is not None:
            env.update(self.environment())
        env.update(PYTHONUNBUFFERED="1", OMNIX_CHILD_TOKEN=self.token)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with self.log_path.open("w", encoding="utf-8") as log_file:
            self.process = subprocess.Popen(self.command(), cwd=str(self.cwd), env=env, stdout=log_file,
                                            stderr=subprocess.STDOUT, creationflags=creationflags)
        self.pid_path.write_text(str(self.process.pid), encoding="utf-8")
        deadline = time.monotonic() + float(self.startup_timeout_s)
        while time.monotonic() < deadline:
            code = self.process.poll()
            if code is not None:
                raise RuntimeError(
                    f"the {self.label} server exited during startup (exit code {code & 0xFFFFFFFF:#x}):\n{self.log_tail()}")
            if self.healthy():
                logger.info("%s ready at %s (pid %s)", self.label, self.base_url, self.process.pid)
                return
            time.sleep(1.0)
        raise RuntimeError(f"the {self.label} server did not load within {self.startup_timeout_s:.0f}s")

    def terminate(self) -> None:
        process, self.process = self.process, None
        pid = process.pid if process is not None and process.poll() is None else None
        if pid is None:
            try:
                pid = int(self.pid_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pid = None
        if pid is not None:
            stop_process_tree(pid)
            if process is not None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning("%s server pid %s did not exit after kill", self.label, pid)
        try:
            self.pid_path.unlink()
        except OSError:
            logger.debug("no pid file for %s", self.label)

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None


__all__ = ["ManagedChildServer", "stop_process_tree"]
