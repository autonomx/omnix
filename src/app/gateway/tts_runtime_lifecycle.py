"""Startup lifecycle for keeping the local chat TTS runtime warm."""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.shared import get_tts_provider

from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_tts_runtime_lifecycle_registered"
_HOOK_SENTINEL = "_omnix_tts_runtime_lifecycle_hook_installed"
_STARTUP_WARMUP_ENV = "OMNIX_TTS_STARTUP_WARMUP"
_WARMUP_SPEAKER_ENV = "OMNIX_TTS_WARMUP_SPEAKER"
_WARMUP_STREAM_ID = "tts-runtime-warmup"
_WARMUP_TEXT = "Audio runtime ready."
_WARMUP_MAX_NEW_TOKENS = 192
_WARMUP_CHUNK_SIZE = 8


@dataclass
class TtsRuntimeLifecycleState:
    status: str = "idle"
    trigger: str | None = None
    provider_class: str | None = None
    provider_name: str | None = None
    speaker: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    model_loaded: bool = False
    graph_warmed: bool = False
    first_chunk_samples: int | None = None
    sample_rate: int | None = None
    error: str | None = None
    warmup_count: int = 0
    unload_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_STATE = TtsRuntimeLifecycleState()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in {"0", "false", "no", "off", "disabled"}


def startup_warmup_enabled() -> bool:
    """Enable real startup warmup by default outside tests."""
    if _STARTUP_WARMUP_ENV in os.environ:
        return _env_flag(_STARTUP_WARMUP_ENV, True)
    return "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ


def _select_warmup_speaker(provider: Any) -> str | None:
    configured = (os.environ.get(_WARMUP_SPEAKER_ENV) or "").strip()
    if configured:
        return configured
    try:
        speakers = provider.get_speakers()
    except Exception:
        return None
    if not isinstance(speakers, list):
        return None
    non_default = [
        str(item.get("id") or "").strip()
        for item in speakers
        if isinstance(item, dict) and str(item.get("id") or "").strip() not in {"", "default"}
    ]
    return non_default[0] if non_default else None


def _public_state(provider: Any | None = None) -> dict[str, Any]:
    with _STATE.lock:
        payload = asdict(_STATE)
    payload.pop("lock", None)
    if provider is not None and hasattr(provider, "get_runtime_status"):
        try:
            payload["provider_runtime"] = provider.get_runtime_status()
        except Exception as exc:
            payload["provider_runtime"] = {"status_error": str(exc)}
    payload["startup_warmup_enabled"] = startup_warmup_enabled()
    payload["startup_warmup_env"] = _STARTUP_WARMUP_ENV
    payload["warmup_speaker_env"] = _WARMUP_SPEAKER_ENV
    return payload


def warm_tts_runtime(trigger: str = "manual") -> dict[str, Any]:
    """Load the singleton model and execute one real graph-backed stream chunk."""
    with _STATE.lock:
        if _STATE.status == "warming":
            return _public_state()
        _STATE.status = "warming"
        _STATE.trigger = trigger
        _STATE.started_at = _utc_now()
        _STATE.completed_at = None
        _STATE.duration_ms = None
        _STATE.error = None
        _STATE.graph_warmed = False
        _STATE.first_chunk_samples = None
        _STATE.sample_rate = None

    started = time.perf_counter()
    stream_log(_WARMUP_STREAM_ID, "lifecycle", "warmup_started", trigger=trigger)
    provider: Any | None = None
    iterator: Any | None = None
    try:
        provider = get_tts_provider()
        if provider is None:
            raise RuntimeError("tts_provider_unavailable")

        provider_class = f"{type(provider).__module__}.{type(provider).__qualname__}"
        provider_name = getattr(provider, "provider_name", None)
        with _STATE.lock:
            _STATE.provider_class = provider_class
            _STATE.provider_name = str(provider_name) if provider_name is not None else None

        start_result = provider.start() if hasattr(provider, "start") else {"running": True}
        if isinstance(start_result, dict) and not bool(start_result.get("running", False)):
            raise RuntimeError(str(start_result.get("error") or start_result.get("message") or "tts_provider_start_failed"))

        speaker = _select_warmup_speaker(provider)
        with _STATE.lock:
            _STATE.speaker = speaker
            _STATE.model_loaded = True

        iterator = provider.generate_audio_stream(
            text=_WARMUP_TEXT,
            speaker=speaker,
            language="English",
            chunk_size=_WARMUP_CHUNK_SIZE,
            temperature=0.6,
            top_k=20,
            top_p=0.85,
            repetition_penalty=1.0,
            append_silence=False,
            max_new_tokens=_WARMUP_MAX_NEW_TOKENS,
            non_streaming_mode=False,
            parity_mode=False,
        )
        audio_chunk, sample_rate, timing = next(iterator)
        samples = len(audio_chunk) if hasattr(audio_chunk, "__len__") else None

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
        except Exception:
            pass

        elapsed_ms = (time.perf_counter() - started) * 1000
        with _STATE.lock:
            _STATE.status = "ready"
            _STATE.completed_at = _utc_now()
            _STATE.duration_ms = round(elapsed_ms, 3)
            _STATE.graph_warmed = True
            _STATE.first_chunk_samples = int(samples) if samples is not None else None
            _STATE.sample_rate = int(sample_rate or 0) or None
            _STATE.warmup_count += 1
        stream_log(
            _WARMUP_STREAM_ID,
            "lifecycle",
            "warmup_completed",
            trigger=trigger,
            elapsed_ms=round(elapsed_ms, 3),
            provider_class=provider_class,
            provider_name=provider_name,
            speaker=speaker,
            first_chunk_samples=samples,
            sample_rate=sample_rate,
            provider_timing=timing,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        with _STATE.lock:
            _STATE.status = "failed"
            _STATE.completed_at = _utc_now()
            _STATE.duration_ms = round(elapsed_ms, 3)
            _STATE.error = str(exc)
            _STATE.model_loaded = bool(
                provider is not None
                and hasattr(provider, "get_runtime_status")
                and provider.get_runtime_status().get("model_loaded")
            )
        stream_log(
            _WARMUP_STREAM_ID,
            "lifecycle",
            "warmup_failed",
            trigger=trigger,
            elapsed_ms=round(elapsed_ms, 3),
            error=repr(exc),
        )
    finally:
        if iterator is not None and hasattr(iterator, "close"):
            try:
                iterator.close()
            except Exception:
                pass

    return _public_state(provider)


def unload_tts_runtime(trigger: str = "manual") -> dict[str, Any]:
    """Unload the cached provider model and release VRAM explicitly."""
    provider: Any | None = None
    started = time.perf_counter()
    stream_log(_WARMUP_STREAM_ID, "lifecycle", "unload_started", trigger=trigger)
    try:
        provider = get_tts_provider()
        if provider is None:
            raise RuntimeError("tts_provider_unavailable")
        stopped = provider.stop() if hasattr(provider, "stop") else False
        if not stopped:
            raise RuntimeError("tts_provider_unload_failed")
        elapsed_ms = (time.perf_counter() - started) * 1000
        with _STATE.lock:
            _STATE.status = "unloaded"
            _STATE.trigger = trigger
            _STATE.completed_at = _utc_now()
            _STATE.duration_ms = round(elapsed_ms, 3)
            _STATE.model_loaded = False
            _STATE.graph_warmed = False
            _STATE.error = None
            _STATE.unload_count += 1
        stream_log(
            _WARMUP_STREAM_ID,
            "lifecycle",
            "unload_completed",
            trigger=trigger,
            elapsed_ms=round(elapsed_ms, 3),
        )
    except Exception as exc:
        with _STATE.lock:
            _STATE.status = "failed"
            _STATE.error = str(exc)
        stream_log(
            _WARMUP_STREAM_ID,
            "lifecycle",
            "unload_failed",
            trigger=trigger,
            error=repr(exc),
        )
    return _public_state(provider)


def register_tts_runtime_lifecycle(gateway: FastAPI) -> None:
    """Register startup warmup and explicit lifecycle inspection routes once."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    async def startup_warmup() -> None:
        if not startup_warmup_enabled():
            with _STATE.lock:
                _STATE.status = "disabled"
                _STATE.trigger = "startup"
            stream_log(_WARMUP_STREAM_ID, "lifecycle", "startup_warmup_disabled")
            return
        await asyncio.to_thread(warm_tts_runtime, "startup")

    gateway.add_event_handler("startup", startup_warmup)

    @gateway.get("/api/tts/runtime/status", include_in_schema=False)
    async def tts_runtime_status() -> dict[str, Any]:
        provider: Any | None = None
        try:
            provider = get_tts_provider()
        except Exception:
            pass
        return _public_state(provider)

    @gateway.post("/api/tts/runtime/warmup", include_in_schema=False)
    async def tts_runtime_warmup() -> dict[str, Any]:
        return await asyncio.to_thread(warm_tts_runtime, "api")

    @gateway.post("/api/tts/runtime/unload", include_in_schema=False)
    async def tts_runtime_unload() -> dict[str, Any]:
        return await asyncio.to_thread(unload_tts_runtime, "api")


def install_tts_runtime_lifecycle_hook() -> None:
    """Install lifecycle registration before the gateway app is constructed."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_tts_runtime_lifecycle(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
