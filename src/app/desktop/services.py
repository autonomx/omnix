"""The model services the desktop supervisor runs, and when (desktop roadmap §4.2).

A model service runs when a bundle that needs it is installed: its models are
in the packs folder and its runtime packs are current. Before a start the
supervisor checks that the service's persisted port is free (a busy port is
reported, never cleared) and that enough memory is left to load it (on
Windows, commit headroom: a load past it freezes the PC).

A service is stopped gracefully (Ctrl+Break on Windows, SIGTERM elsewhere), so
its shutdown releases the GPU model ownership it holds in PostgreSQL; only one
that does not exit within 20 seconds is killed. A service that exits on its
own is restarted after 30, 60 and 120 seconds (a crashed process cannot release
its ownership lease, which expires on its own in under three minutes), then
reported as failed until its packs change.

States reported to the shell: ``starting``, ``running``, ``stopped``,
``blocked`` (port busy or not enough memory; retried), ``failed``.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import urllib.request
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.desktop.env import LaunchConfig, service_environment
from app.models import catalog as model_catalog
from app.models.catalog import Catalog
from app.models.packs import ModelStore, RuntimeStore

logger = logging.getLogger(__name__)

RESTART_DELAYS_SECONDS = (30.0, 60.0, 120.0)
HEALTHY_SECONDS = 600.0
STOP_SECONDS = 20.0
# Without a measured requirement: the model files' size, half again, plus room for the service itself.
HEADROOM_FACTOR = 1.5
HEADROOM_BASE_BYTES = 2 * 2**30
# A started service's memory is reserved for this long (or until it is healthy, if later): its commit charge
# grows while it loads, so the next service's headroom check must not count that memory as free.
SETTLE_SECONDS = 90.0


@dataclass
class ServicePlan:
    """What one service needs from the packs."""

    service: str
    entry: str
    runtime: str
    site_dirs: list[Path]
    bundles: list[str]
    model_dir: Path | None = None
    needed_bytes: int = 0
    # Each bundle's requirement and models: a service that serves two bundles loads both bundles' models.
    requirements: list[tuple[int, list[str]]] = field(default_factory=list)


@dataclass
class _Running:
    plan: ServicePlan
    process: subprocess.Popen[bytes]
    started: float
    restarts: int = 0


@dataclass
class ServiceState:
    state: str = "stopped"
    message: str = ""
    restarts: int = 0
    failed_signature: str = ""
    # A restart after a crash waits until then (time.monotonic()).
    restart_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def _process_group() -> dict[str, Any]:
    """Each service in its own process group: Windows sends it Ctrl+Break for a graceful stop, macOS signals the
    whole group, so nothing a service started outlives it."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _signal_group(process: subprocess.Popen[bytes], signum: int) -> None:
    try:
        os.killpg(process.pid, signum)
    except (OSError, AttributeError):
        process.send_signal(signum)


def stop_gracefully(process: subprocess.Popen[bytes], timeout: float = STOP_SECONDS) -> None:
    """Ask the service to shut down (its shutdown handlers release its GPU ownership); kill it only if it hangs."""
    if process.poll() is not None:
        return
    with contextlib.suppress(OSError, ValueError):
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            process.kill()
        else:
            _signal_group(process, signal.SIGKILL)


def plans(config: LaunchConfig, catalog: Catalog, runtimes: RuntimeStore, models: ModelStore,
          platform: str | None = None) -> dict[str, ServicePlan]:
    """The services this machine should run now, from the installed bundles."""
    platform = platform or model_catalog.current_platform()
    found: dict[str, ServicePlan] = {}
    for bundle in catalog.bundles.values():
        variant = bundle.variant(platform)
        if variant is None:
            continue
        closure = catalog.runtime_closure(variant.runtimes)
        if not all(models.installed(model_id) for model_id in variant.models):
            continue
        # An installed pack runs even when an app update shipped a newer one (the user downloads it when they
        # choose); it stops only while that newer version replaces it.
        if not all(runtimes.installed(pack.id) and not runtimes.updating(pack.id) for pack in closure):
            continue
        service_pack = next(pack for pack in reversed(closure) if pack.service)
        service = service_pack.service
        entry = "stt-mlx" if service_pack.accelerator == "mlx" else service
        sites = [runtimes.site(service_pack.id)] + ([runtimes.site(service_pack.base)] if service_pack.base else [])
        plan = found.get(service)
        if plan is None:
            plan = found[service] = ServicePlan(service, entry, service_pack.id, sites, [])
        plan.bundles.append(bundle.id)
        if variant.min_commit_mb is not None:
            need = variant.min_commit_mb * 2**20
        else:
            weights = sum(catalog.model(model_id).size for model_id in variant.models)
            need = int(weights * HEADROOM_FACTOR) + HEADROOM_BASE_BYTES
        plan.requirements.append((need, list(variant.models)))
        if service == "tts":
            plan.model_dir = models.snapshot(variant.models[0])
    for plan in found.values():
        # The largest bundle's measured need, plus the other bundles' models that it does not already load.
        largest, counted = max(plan.requirements, key=lambda item: item[0])
        extra = {model_id for _, model_ids in plan.requirements for model_id in model_ids} - set(counted)
        plan.needed_bytes = largest + int(sum(catalog.model(model_id).size for model_id in extra) * HEADROOM_FACTOR)
    return found


def _available_commit() -> int | None:
    from app.providers.host_memory import available_commit_bytes

    return available_commit_bytes()


def _healthy(port: int) -> bool:
    """The service answers and its models are loaded: STT answers ``"ok": false`` while it warms its models."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:  # noqa: S310
            if response.status != 200:
                return False
            body = response.read()
    except OSError:
        return False
    try:
        answer = json.loads(body)
    except ValueError:
        return True
    return not (isinstance(answer, dict) and answer.get("ok") is False)


class ModelServices:
    """Starts, watches and stops the model services; ``reconcile`` is called on a timer and after installs."""

    def __init__(self, config: LaunchConfig, *, python: str, service_token: Callable[[], str],
                 emit: Callable[[dict[str, Any]], None], logs: Path, app_source: Path,
                 catalog: Catalog | None = None, port_free: Callable[[int], bool] | None = None,
                 available_commit: Callable[[], int | None] = _available_commit,
                 launch: Callable[..., subprocess.Popen[bytes]] | None = None,
                 healthy: Callable[[int], bool] | None = None,
                 stop_process: Callable[[Any], None] | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        from app.desktop.supervise import port_free as _port_free

        self.config = config
        self.python = python
        self.service_token = service_token
        self.emit = emit
        self.logs = logs
        self.app_source = app_source
        self.catalog = catalog or model_catalog.load()
        self.runtimes = RuntimeStore(config.packs, self.catalog)
        self.models = ModelStore(config.models_cache, self.catalog)
        self.port_free = port_free or _port_free
        self.available_commit = available_commit
        self.launch = launch or subprocess.Popen
        self.healthy = healthy or _healthy
        self.stop_process = stop_process or stop_gracefully
        self.clock = clock or time.monotonic
        self.running: dict[str, _Running] = {}
        self.states: dict[str, ServiceState] = {}
        self._lock = threading.Lock()

    def _report(self, service: str, state: str, message: str = "", **extra: Any) -> None:
        current = self.states.setdefault(service, ServiceState())
        if (current.state, current.message) == (state, message):
            return
        current.state, current.message = state, message
        current.extra = extra
        self.emit({"event": "service", "service": service, "state": state, "message": message, **extra})

    def status(self) -> dict[str, dict[str, Any]]:
        return {name: {"state": item.state, "message": item.message, "restarts": item.restarts, **item.extra}
                for name, item in self.states.items()}

    def _signature(self, plan: ServicePlan) -> str:
        return "|".join([plan.runtime, *map(str, plan.site_dirs), str(plan.model_dir or ""), *sorted(plan.bundles)])

    def _loading(self) -> list[_Running]:
        """Services still loading: started, and not yet both healthy and settled."""
        now = time.monotonic()
        return [item for name, item in self.running.items()
                if self.states.get(name, ServiceState()).state == "starting" or now - item.started < SETTLE_SECONDS]

    def _start(self, plan: ServicePlan, restarts: int = 0) -> None:
        port = self.config.port(plan.service)
        if not self.port_free(port):
            self._report(plan.service, "blocked", f"port {port} is in use by another program", port=port)
            return
        loading = self._loading()
        if any(self.states.get(item.plan.service, ServiceState()).state == "starting" for item in loading):
            # One model loads at a time, so each headroom check sees the memory the others really take.
            self._report(plan.service, "waiting", "waiting for another model to finish loading")
            return
        available = self.available_commit()
        if available is not None:
            available -= sum(item.plan.needed_bytes for item in loading)
        if available is not None and available < plan.needed_bytes:
            if loading:
                # Checked again on the next pass, once the loading service's real use shows in the figure.
                self._report(plan.service, "waiting", "waiting for another model to finish loading")
                return
            self._report(plan.service, "blocked",
                         f"not enough memory to load it: {available / 2**30:.1f} GB free, about "
                         f"{plan.needed_bytes / 2**30:.1f} GB needed; close other programs")
            return
        env = service_environment(self.config, plan.service, service_token=self.service_token(),
                                  site_dirs=plan.site_dirs, model_dir=plan.model_dir)
        # A development interpreter (no ._pth) finds the app source through PYTHONPATH; -S keeps its packages out.
        env["PYTHONPATH"] = str(self.app_source)
        # macOS: the service stops itself once this supervisor is gone (Windows: the Job Object ends it).
        env["OMNIX_DESKTOP_PARENT_PID"] = str(os.getpid())
        self.logs.mkdir(parents=True, exist_ok=True)
        log = (self.logs / f"{plan.service}.log").open("ab")
        self._report(plan.service, "starting", port=port)
        process = self.launch([self.python, "-S", "-m", "app.desktop.service_boot", plan.entry], env=env,
                              stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                              cwd=str(self.config.data_dir), **_process_group())
        log.close()
        self.running[plan.service] = _Running(plan, process, time.monotonic(), restarts)
        self.states[plan.service].restarts = restarts

    def _stop(self, service: str) -> None:
        running = self.running.pop(service, None)
        if running is None:
            return
        self.stop_process(running.process)
        self._report(service, "stopped")

    def reconcile(self) -> None:
        with self._lock:
            try:
                wanted = plans(self.config, self.catalog, self.runtimes, self.models)
            except Exception as exc:  # a broken pack must not stop the supervisor
                logger.warning("Could not plan the model services", exc_info=True)
                self.emit({"event": "service", "service": "*", "state": "failed", "message": str(exc)})
                return
            for service in list(self.running):
                plan = wanted.get(service)
                if plan is None or self._signature(plan) != self._signature(self.running[service].plan):
                    self._stop(service)
            for service, plan in wanted.items():
                state = self.states.setdefault(service, ServiceState())
                running = self.running.get(service)
                if running is not None:
                    code = running.process.poll()
                    if code is None:
                        if state.state == "starting" and self.healthy(self.config.port(service)):
                            self._report(service, "running", port=self.config.port(service))
                        if running.restarts and time.monotonic() - running.started > HEALTHY_SECONDS:
                            running.restarts = 0
                        continue
                    del self.running[service]
                    if running.restarts >= len(RESTART_DELAYS_SECONDS):
                        state.failed_signature = self._signature(plan)
                        self._report(service, "failed", f"it keeps stopping (exit {code}); see {service}.log")
                        continue
                    delay = RESTART_DELAYS_SECONDS[running.restarts]
                    state.restarts = running.restarts + 1
                    state.restart_at = self.clock() + delay
                    self._report(service, "restarting", f"it stopped (exit {code}); starting again in {delay:.0f} s")
                    continue
                if state.state == "failed" and state.failed_signature == self._signature(plan):
                    continue  # a new install (another signature) gets a fresh start
                if state.state == "restarting":
                    if self.clock() < state.restart_at:
                        continue
                    self._start(plan, restarts=state.restarts)
                    continue
                self._start(plan)
            for service in list(self.states):
                if service not in wanted and service not in self.running and self.states[service].state != "stopped":
                    self._report(service, "stopped")

    def stop_all(self) -> None:
        with self._lock:
            for service in list(self.running):
                self._stop(service)


__all__ = ["ModelServices", "ServicePlan", "plans", "stop_gracefully"]
