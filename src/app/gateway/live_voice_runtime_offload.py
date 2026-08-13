"""Keep live-voice persistence and provider lookup off the gateway event loop."""
from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any

from fastapi import FastAPI

from app import shared

from .tts_stream_diagnostics import active_streams_snapshot, stream_log

_HOOK_SENTINEL = "_omnix_live_voice_runtime_offload_hook_installed"
_STATE_SENTINEL = "_omnix_live_voice_runtime_offload_registered"
_DEFAULT_PROVIDER_REFRESH_SECONDS = 5.0
_DEFAULT_DELIVERY_QUEUE_SIZE = 128
_PROVIDER_RESOLVER: CachedTtsProviderResolver | None = None


def _env_float(name: str, default: float, *, minimum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class DeliveryPersistenceWorker:
    """Serialize delivery checkpoints on a bounded daemon-worker queue."""

    def __init__(
        self,
        persist: Callable[[dict[str, Any]], None],
        *,
        max_queue_size: int | None = None,
        log: Callable[..., None] = stream_log,
    ) -> None:
        self._persist = persist
        self._log = log
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(
            maxsize=max_queue_size
            or _env_int(
                "OMNIX_LIVE_VOICE_DELIVERY_QUEUE_SIZE",
                _DEFAULT_DELIVERY_QUEUE_SIZE,
                minimum=8,
                maximum=2048,
            )
        )
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def enqueue(self, details: Mapping[str, Any]) -> None:
        payload = dict(details)
        self._ensure_started()
        try:
            self._queue.put_nowait(payload)
            return
        except queue.Full:
            pass

        # Delivery checkpoints are cumulative. Prefer the newest checkpoint when
        # persistence temporarily falls behind instead of blocking the caller.
        try:
            self._queue.get_nowait()
            self._queue.task_done()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._log(
                "gateway-live-voice-runtime",
                "runtime",
                "delivery_persistence_checkpoint_dropped",
            )

    def stop(self, timeout: float = 0.25) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            thread = self._thread
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(None)
            except (queue.Empty, queue.Full):
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None or self._stopped:
                return
            self._thread = threading.Thread(
                target=self._run,
                name="omnix-live-voice-delivery",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                if payload is None:
                    return
                started_at = time.perf_counter()
                self._persist(payload)
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                if elapsed_ms >= 25.0:
                    self._log(
                        "gateway-live-voice-runtime",
                        "runtime",
                        "delivery_persistence_completed",
                        elapsed_ms=round(elapsed_ms, 3),
                    )
            except Exception as exc:  # pragma: no cover - defensive persistence guard.
                self._log(
                    "gateway-live-voice-runtime",
                    "runtime",
                    "delivery_persistence_failed",
                    error_type=type(exc).__name__,
                )
            finally:
                self._queue.task_done()


class CachedTtsProviderResolver:
    """Return a warmed provider immediately and refresh settings while idle."""

    def __init__(
        self,
        resolve: Callable[..., Any],
        *,
        active_streams: Callable[[], dict[str, Any]] = active_streams_snapshot,
        refresh_seconds: float | None = None,
        log: Callable[..., None] = stream_log,
    ) -> None:
        self._resolve = resolve
        self._active_streams = active_streams
        self._refresh_seconds = refresh_seconds or _env_float(
            "OMNIX_LIVE_VOICE_PROVIDER_REFRESH_SECONDS",
            _DEFAULT_PROVIDER_REFRESH_SECONDS,
            minimum=0.25,
        )
        self._log = log
        self._lock = threading.Lock()
        self._provider: Any = None
        self._resolved_at = 0.0
        self._refreshing = False
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="omnix-live-voice-provider-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def stop(self, timeout: float = 0.25) -> None:
        self._stop_event.set()
        with self._lock:
            thread = self._monitor_thread
            self._monitor_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def get(self, provider_name: str | None = None) -> Any:
        if provider_name is not None:
            return self._resolve(provider_name)

        now = time.perf_counter()
        with self._lock:
            provider = self._provider
            stale = provider is not None and now - self._resolved_at >= self._refresh_seconds

        if provider is None:
            # Startup warming normally makes this unreachable for served requests.
            return self.refresh()
        if stale and not self._active_streams():
            self.refresh_in_background()
        return provider

    def refresh(self) -> Any:
        if not self._begin_refresh():
            with self._lock:
                return self._provider
        return self._run_started_refresh()

    def refresh_in_background(self) -> bool:
        if not self._begin_refresh():
            return False
        threading.Thread(
            target=self._run_started_refresh,
            name="omnix-live-voice-provider-refresh",
            daemon=True,
        ).start()
        return True

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(self._refresh_seconds):
            if not self._active_streams():
                self.refresh()

    def _begin_refresh(self) -> bool:
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
            return True

    def _run_started_refresh(self) -> Any:
        started_at = time.perf_counter()
        resolved: Any = None
        error_type: str | None = None
        try:
            resolved = self._resolve()
            return resolved
        except Exception as exc:  # pragma: no cover - preserve the previous provider.
            error_type = type(exc).__name__
            with self._lock:
                return self._provider
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            with self._lock:
                if resolved is not None:
                    self._provider = resolved
                    self._resolved_at = time.perf_counter()
                provider = self._provider
                self._refreshing = False
            self._log(
                "gateway-live-voice-runtime",
                "runtime",
                "tts_provider_cache_refreshed" if error_type is None else "tts_provider_cache_refresh_failed",
                elapsed_ms=round(elapsed_ms, 3),
                error_type=error_type,
                provider_class=(
                    f"{type(provider).__module__}.{type(provider).__qualname__}"
                    if provider is not None
                    else None
                ),
                provider_name=getattr(provider, "provider_name", None),
            )


def get_cached_live_tts_provider(provider_name: str | None = None) -> Any:
    """Return the warmed shared provider without coupling to the websocket module."""
    resolver = _PROVIDER_RESOLVER
    if resolver is None:
        return shared.get_tts_provider(provider_name)
    return resolver.get(provider_name)


def install_live_voice_runtime_offload_hook() -> None:
    """Install bounded persistence and provider warming before app creation."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    from . import live_voice_stream_diagnostics

    persistence_worker = DeliveryPersistenceWorker(live_voice_stream_diagnostics._persist_delivery)
    live_voice_stream_diagnostics._persist_delivery = persistence_worker.enqueue

    global _PROVIDER_RESOLVER
    provider_resolver = CachedTtsProviderResolver(shared.get_tts_provider)
    _PROVIDER_RESOLVER = provider_resolver

    original_init = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        is_gateway = kwargs.get("title") == "Omnix Web Gateway"
        if not is_gateway and args:
            is_gateway = args[0] == "Omnix Web Gateway"
        if not is_gateway or getattr(self.state, _STATE_SENTINEL, False):
            return
        setattr(self.state, _STATE_SENTINEL, True)
        self.state.live_voice_delivery_persistence_worker = persistence_worker
        self.state.live_voice_tts_provider_resolver = provider_resolver

        async def startup() -> None:
            await asyncio.to_thread(provider_resolver.refresh)
            provider_resolver.start()
            stream_log(
                "gateway-live-voice-runtime",
                "runtime",
                "live_voice_runtime_offload_started",
            )

        async def shutdown() -> None:
            provider_resolver.stop()
            persistence_worker.stop()

        self.router.add_event_handler("startup", startup)
        self.router.add_event_handler("shutdown", shutdown)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
