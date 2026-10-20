"""The GPU swap controller (Voice Studio Phase 1 §6): swap, don't stack, on one 24 GB GPU.

A job that needs a TTS engine other than the one loaded records a swap request
and defers itself (``defer_job``, no attempt spent). The controller, one at a
time across processes through a fenced, expiring lease in PostgreSQL:

1. never starts a swap while a live-session lease exists (live speech wins), nor
   while a TTS job runs on the loaded engine (it finishes there first);
2. serves requests in arrival order: unloads the selected engine, loads the
   requested one, and marks its requests served, so deferred jobs run as a group;
3. restores the selected engine when no job waits for or runs on the swapped
   engine, or when the group has held the GPU past its cap;
4. ends the swap when live speech interrupted it (the TTS service switched the
   selected engine back for a live request); interrupted jobs re-request;
5. restores the selected engine after a crash, when a swap lease expires.

A load that does not fit in the free VRAM fails its requests at once with what
to free, instead of waiting: the resident models never leave on their own.
Swaps need the TTS service (remote TTS); with in-process TTS pinned jobs fail
as in Phase 0.
"""
from __future__ import annotations

import contextvars
import logging
import os
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any, Callable

logger = logging.getLogger(__name__)

HOLD_CAP_SECONDS = 600.0
LEASE_SECONDS = 60.0
TICK_SECONDS = 2.0
# Host memory (Windows commit) of engines that run in their own process, measured on the 4090 target.
HOST_MEMORY_GB = {"fish-s2-pro": 24.0}
# Host memory an unload gives back: all of Fish's process; part of an in-process engine (measured on the
# TTS service: VoiceDesign about 1.9 GB, credited conservatively).
UNLOAD_FREES_GB = {"fish-s2-pro": 24.0, "qwen3-tts-voicedesign": 1.5}
_GB = 1024 ** 3


@dataclass
class ServiceHealth:
    loaded_engine: str
    swap_fence: int | None
    vram_free_bytes: int | None = None
    ok: bool = True
    host_free_bytes: int | None = None


class SwapServiceError(RuntimeError):
    pass


class TtsSwapService:
    """The TTS service's swap endpoints, over the gateway's shared HTTP client."""

    def __init__(self, base_url: str, http: Any = None) -> None:
        from app.runtime.http_client import shared_http_client

        self.base_url = base_url.rstrip("/")
        self.http = http or shared_http_client("tts-service")

    def health(self) -> ServiceHealth:
        response = self.http.get(self.base_url + "/health", timeout=5, retry=False)
        response.raise_for_status()
        data = response.json()
        swap = data.get("swap") or {}
        gpu = data.get("gpu") or {}
        host = data.get("host") or {}
        return ServiceHealth(
            loaded_engine=str(data.get("provider") or ""),
            swap_fence=int(swap["fence"]) if swap.get("fence") is not None else None,
            vram_free_bytes=int(gpu["vram_free_bytes"]) if gpu.get("vram_free_bytes") is not None else None,
            ok=bool(data.get("ok")),
            host_free_bytes=int(host["commit_free_bytes"]) if host.get("commit_free_bytes") is not None else None,
        )

    def _post(self, path: str, provider: str, fence: int, restore: str = "") -> dict[str, Any]:
        from app.security.service_token import service_headers

        response = self.http.post(
            self.base_url + path,
            json={"provider": provider, "fence_token": fence, "restore_provider": restore},
            timeout=900, headers=service_headers(), retry=False,
        )
        if response.status_code >= 400:
            raise SwapServiceError(f"{path} answered {response.status_code}: {response.text[:300]}")
        return response.json()

    def swap(self, engine: str, fence: int, restore: str) -> dict[str, Any]:
        return self._post("/api/tts/engine/swap", engine, fence, restore)

    def restore(self, engine: str, fence: int) -> dict[str, Any]:
        return self._post("/api/tts/engine/restore", engine, fence)


@dataclass
class SwapController:
    service: Any
    selected_engine: Callable[[], str]
    store: Any = None
    holder_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:swap")
    hold_cap_seconds: float = HOLD_CAP_SECONDS
    lease_seconds: float = LEASE_SECONDS
    vram_needed_gb: Callable[[str], float | None] = field(default=lambda engine: None)
    # How long an engine stays swapped in after its last job (voice design sessions).
    linger_seconds: Callable[[str], float] = field(default=lambda engine: 0.0)
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    # A failed restore (the selected engine would not load) is tried again this often.
    restore_retry_seconds: float = 30.0
    _fence: int | None = None
    _restore_attempted_at: float = 0.0

    def __post_init__(self) -> None:
        if self.store is None:
            from app.persistence import tts_swap

            self.store = tts_swap

    # -- one step -------------------------------------------------------------------------

    def tick(self) -> str:
        """Advance the swap state machine once; returns what it did (for tests and diagnostics)."""
        self.store.close_finished_requests()
        state = self.store.swap_state()
        if not state.idle:
            if state.lease_expired and state.fence_token != self._fence:
                return self._recover(state)
            if state.fence_token != self._fence:
                return "held-elsewhere"
            if state.phase == "restoring":
                return self._retry_restore(state)
            return self._manage_active(state)
        return self._start_swap()

    def _retry_restore(self, state: Any) -> str:
        """A restore failed (host memory was short, say): try again every ``restore_retry_seconds``.

        Meanwhile no other engine can be swapped in, so the jobs waiting for one fail with the reason
        instead of waiting for as long as the restore keeps failing.
        """
        restore = str(state.restore_engine or self.selected_engine())
        # Requests for the engine being restored keep waiting: the next successful retry serves them.
        for engine in sorted({str(request["engine"]) for request in self.store.pending_swap_requests()} - {restore}):
            self.store.resolve_swap_requests(
                engine, "failed", f"the selected engine {restore} could not be loaded again ({state.detail or 'restore failed'}); "
                "free memory or select another engine, then try again")
        if time.monotonic() - self._restore_attempted_at < self.restore_retry_seconds:
            self.store.update_swap(int(state.fence_token), lease_seconds=self.lease_seconds)
            return "restore-waiting"
        engine = str(state.restore_engine or self.selected_engine())
        self._restore(int(state.fence_token), engine, detail="restored after a retry")
        return "restored:" + engine if self._fence is None else "restore-failed:" + engine

    def _start_swap(self) -> str:
        requests = self.store.pending_swap_requests()
        if not requests:
            return "idle"
        health = self.service.health()
        loaded = health.loaded_engine
        if any(request["engine"] == loaded for request in requests):
            # The engine is already there (it was never swapped out, or live speech brought it back).
            self.store.resolve_swap_requests(loaded, "served")
            return f"served:{loaded}"
        if self.store.live_session_active():
            return "waiting-for-live-speech"
        engine = requests[0]["engine"]
        selected = self.selected_engine()
        shortfall = self._vram_shortfall(engine, health)
        if shortfall:
            self.store.resolve_swap_requests(engine, "failed", shortfall)
            return f"failed:{engine}"
        if self.store.tts_jobs_running():
            # A job already running on the loaded engine finishes on it before the engine is unloaded.
            return "waiting-for-running-jobs"
        fence = self.store.begin_swap(self.holder_id, engine=engine, restore_engine=selected,
                                      lease_seconds=self.lease_seconds)
        if fence is None:
            return "held-elsewhere"
        self._fence = fence
        try:
            with self._renewing(fence):
                self.service.swap(engine, fence, selected)
        except Exception as exc:
            logger.warning("Swapping %s in failed: %s", engine, exc)
            self.store.resolve_swap_requests(engine, "failed", f"{engine} could not be loaded: {exc}")
            self._restore(fence, selected, detail=f"swap to {engine} failed")
            return f"failed:{engine}"
        self.store.update_swap(fence, phase="active", lease_seconds=self.lease_seconds)
        self.store.resolve_swap_requests(engine, "served")
        return f"swapped:{engine}"

    def _manage_active(self, state: Any) -> str:
        fence = int(state.fence_token)
        health = self.service.health()
        if health.swap_fence != fence or health.loaded_engine != state.engine:
            # Live speech took the GPU back (or the service restarted): the swap is over.
            self.store.end_swap(fence, interrupted=True, detail="live speech took the GPU back")
            self._fence = None
            return "interrupted"
        engine = str(state.engine)
        pending = self.store.pending_swap_requests()
        if any(request["engine"] == engine for request in pending):
            self.store.resolve_swap_requests(engine, "served")
        held = (self.now() - state.group_started_at).total_seconds() if state.group_started_at else 0.0
        others_waiting = any(request["engine"] != engine for request in pending)
        in_use = self.store.engine_in_use(engine, linger_seconds=0.0 if others_waiting else self.linger_seconds(engine))
        if in_use and not (held >= self.hold_cap_seconds and others_waiting):
            self.store.update_swap(fence, lease_seconds=self.lease_seconds)
            return f"holding:{engine}"
        restore = str(state.restore_engine or self.selected_engine())
        self._restore(fence, restore, detail="hold cap reached" if in_use else "group finished")
        return f"restored:{restore}"

    def _restore(self, fence: int, engine: str, *, detail: str) -> None:
        self._restore_attempted_at = time.monotonic()
        self.store.update_swap(fence, phase="restoring", lease_seconds=self.lease_seconds)
        try:
            with self._renewing(fence):
                self.service.restore(engine, fence)
        except Exception as exc:
            # Keep the lease to expire: recovery (here or in another process) retries the restore.
            logger.warning("Restoring %s failed: %s", engine, exc)
            self.store.update_swap(fence, detail=f"restore of {engine} failed: {exc}")
            return
        self.store.end_swap(fence, detail=detail)
        self.store.resolve_swap_requests(engine, "served")
        self._fence = None

    @contextmanager
    def _renewing(self, fence: int) -> Iterator[None]:
        """Keep the lease alive while a load runs: a 12 GB engine can take longer than one lease, and an
        expired lease would let another process "recover" and load a second engine beside this one."""
        stop = threading.Event()
        interval = max(1.0, self.lease_seconds / 3)

        def renew() -> None:
            from app.persistence.tts_swap import SwapFenceLost

            while not stop.wait(interval):
                try:
                    self.store.update_swap(fence, lease_seconds=self.lease_seconds)
                except SwapFenceLost:
                    logger.warning("The swap lease was taken over during a load")
                    return
                except Exception as exc:  # a database blip: try again next interval
                    logger.warning("Renewing the swap lease failed: %s", exc)

        thread = threading.Thread(target=contextvars.copy_context().run, args=(renew,),
                                  name="omnix-swap-lease", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)

    @staticmethod
    def _host_shortfall(engine: str, health: ServiceHealth) -> str:
        """An engine in its own process (Fish) needs host memory too: refuse rather than page for minutes."""
        needed = HOST_MEMORY_GB.get(engine)
        if needed is None or health.host_free_bytes is None:
            return ""
        # Unloading the current engine gives back what it holds (all of a separate process, part of an
        # in-process one).
        available = health.host_free_bytes / _GB + UNLOAD_FREES_GB.get(health.loaded_engine, 0.0)
        if available >= needed + 2.0:  # 2 GB left for the rest of the machine
            return ""
        return (f"{engine} needs about {needed:.0f} GB of free host memory to load but only {available:.1f} GB "
                "would be free; close other programs or stop other model services")

    def _recover(self, state: Any) -> str:
        """A swap lease expired (its controller crashed): restore the selected engine."""
        fence = self.store.begin_swap(self.holder_id, engine=str(state.engine or ""),
                                      restore_engine=str(state.restore_engine or self.selected_engine()),
                                      lease_seconds=self.lease_seconds)
        if fence is None:
            return "held-elsewhere"
        self._fence = fence
        self._restore(fence, str(state.restore_engine or self.selected_engine()), detail="recovered after a crash")
        return "recovered"

    def _vram_shortfall(self, engine: str, health: ServiceHealth) -> str:
        host = self._host_shortfall(engine, health)
        if host:
            return host
        needed = self.vram_needed_gb(engine)
        if needed is None or health.vram_free_bytes is None:
            return ""
        current = self.vram_needed_gb(health.loaded_engine) or 0.0
        available = health.vram_free_bytes / _GB + current  # the current engine is unloaded first
        if available >= needed:
            return ""
        return (f"{engine} needs about {needed:.1f} GB of VRAM but only {available:.1f} GB would be free; "
                "unload the local LLM model or choose a smaller one")


def vram_estimate(engine: str) -> float | None:
    """The catalog's VRAM estimate for an engine id, matched by provider id."""
    from .model_catalog import SPEECH_MODELS

    estimates = {"faster-qwen3-tts": 4.0, "fish-s2-pro": 12.0, "qwen3-tts-voicedesign": 7.0, "omnivoice": 3.0}
    if engine in estimates:
        return estimates[engine]
    for model in SPEECH_MODELS:
        if model.id == engine:
            return model.vram_gb
    return None


DESIGN_LINGER_SECONDS = 120.0


def swap_linger_seconds(engine: str) -> float:
    """Voice-design engines stay loaded between previews of one session; others restore at once."""
    from app.providers.catalog import VOICE_DESIGN, provider_supports

    try:
        return DESIGN_LINGER_SECONDS if provider_supports(engine, VOICE_DESIGN, "tts") else 0.0
    except Exception:
        logger.debug("Unknown engine %s has no linger", engine, exc_info=True)
        return 0.0


def swaps_enabled() -> bool:
    """Swaps need the TTS service (remote TTS) and PostgreSQL coordination."""
    try:
        from app.persistence.runtime import uses_postgresql_runtime
        from app.runtime.config import get_runtime_config

        return bool(get_runtime_config().use_remote_tts) and uses_postgresql_runtime()
    except Exception:
        return False


class SwapControllerLoop:
    """Runs ``SwapController.tick`` every couple of seconds in a worker process."""

    def __init__(self, controller: SwapController, *, interval: float = TICK_SECONDS) -> None:
        self.controller = controller
        self.interval = interval
        self.last_action = ""
        self.last_error = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="omnix-tts-swap-controller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.last_action = self.controller.tick()
                self.last_error = ""
            except Exception as exc:  # one bad tick must not stop the loop
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("TTS swap controller tick failed: %s", exc)
            self._stop.wait(self.interval)

    def snapshot(self) -> dict[str, Any]:
        return {"last_action": self.last_action, "last_error": self.last_error,
                "running": bool(self._thread and self._thread.is_alive()), "at": time.time()}


def create_swap_controller_worker() -> Any:
    """The voice feature's background worker: a swap controller in each job-worker process."""
    import asyncio

    from app.runtime.background import BackgroundWorker
    from app.runtime.capabilities import RuntimeCapability
    from app.runtime.config import get_runtime_config

    if not swaps_enabled():
        return None
    tts = get_runtime_config().tts
    endpoint = tts.url if tts is not None else ""
    if not endpoint:
        return None
    from app.providers.service import selected_tts_provider_id

    loop = SwapControllerLoop(SwapController(TtsSwapService(endpoint), selected_engine=selected_tts_provider_id,
                                             vram_needed_gb=vram_estimate, linger_seconds=swap_linger_seconds))

    async def startup() -> None:
        await asyncio.to_thread(loop.start)

    async def shutdown() -> None:
        await asyncio.to_thread(loop.stop)

    return BackgroundWorker(name="tts-swap-controller", monitor=loop, startup=(startup,), shutdown=(shutdown,),
                            requires=frozenset({RuntimeCapability.RUN_JOB_WORKERS}))


__all__ = [
    "SwapController",
    "SwapControllerLoop",
    "SwapServiceError",
    "TtsSwapService",
    "create_swap_controller_worker",
    "swaps_enabled",
    "vram_estimate",
]
