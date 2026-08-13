"""Side-effect-free first-clause TTS prefetch for accepted live speculation."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import shared
from app.live_speech.performance_contract import apply_performance_plan_to_provider
from app.shared import remove_emojis

from . import tts_live_call_websocket
from .tts_stream_contract import TtsStreamRequest, audio_chunk_to_pcm16_bytes
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_live_speculative_tts_routes_registered"
_HOOK_SENTINEL = "_omnix_live_speculative_tts_hook_installed"
_CACHE_TTL_SECONDS = 45.0
_MAX_CACHE_ENTRIES = 16
_WAIT_SLICE_SECONDS = 0.05
_CACHE_KEY_KWARGS = frozenset(
    {
        "chunk_size",
        "temperature",
        "top_k",
        "top_p",
        "repetition_penalty",
        "append_silence",
        "non_streaming_mode",
        "parity_mode",
    }
)
_ONLY_PUNCTUATION = re.compile(r"^[\W_]+$", re.UNICODE)

# Faster Qwen3 TTS explicitly declares that it does not support concurrent
# generation. Wrong hypotheses may still be winding down when the final answer
# begins, so all real provider calls share one lock. Accepted cache replay never
# takes this lock and therefore remains immediate.
_PROVIDER_GENERATION_LOCK = threading.RLock()


class SpeculativeTtsPrefetchRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    request: TtsStreamRequest


@dataclass
class _CachedPcmChunk:
    pcm_bytes: bytes
    sample_rate: int
    timing: Any


@dataclass
class _SpeculativeTtsEntry:
    generation_id: str
    key: str
    created_at: float
    text: str
    speaker: str
    language: str
    stable_kwargs: dict[str, Any]
    chunks: list[_CachedPcmChunk] = field(default_factory=list)
    accepted: bool = False
    claimed: bool = False
    completed: bool = False
    cancelled: bool = False
    error: str | None = None
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )


@dataclass(frozen=True)
class _CacheClaim:
    entry: _SpeculativeTtsEntry
    remainder_text: str


_ENTRIES: dict[str, _SpeculativeTtsEntry] = {}
_CACHE_LOCK = threading.RLock()


class _PrefetchingProviderProxy:
    """Delegate provider calls, replaying accepted speculative PCM when available."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def generate_audio_stream(
        self,
        *,
        text: str,
        speaker: str | None = None,
        language: str = "en",
        **kwargs: Any,
    ) -> Iterator[tuple[bytes, int, Any]]:
        claim = _claim_entry(text, speaker, language, kwargs)
        if claim is None:
            yield from _locked_provider_stream(
                self._provider,
                text=text,
                speaker=speaker,
                language=language,
                kwargs=kwargs,
            )
            return

        entry = claim.entry
        stream_log(
            "gateway-live-speculative-tts",
            "provider",
            "speculative_tts_cache_claimed",
            generation_id=entry.generation_id,
            buffered_chunk_count=len(entry.chunks),
            completed=entry.completed,
            prefix_match=bool(claim.remainder_text),
            remainder_text_length=len(claim.remainder_text),
        )
        index = 0
        emitted = 0
        replay_completed = False
        try:
            while True:
                with entry.condition:
                    while (
                        index >= len(entry.chunks)
                        and not entry.completed
                        and not entry.cancelled
                        and entry.error is None
                    ):
                        entry.condition.wait(_WAIT_SLICE_SECONDS)
                    available = list(entry.chunks[index:])
                    index += len(available)
                    terminal = (
                        entry.completed
                        or entry.cancelled
                        or entry.error is not None
                    )
                    error = entry.error
                for chunk in available:
                    emitted += 1
                    yield chunk.pcm_bytes, chunk.sample_rate, {
                        **(
                            chunk.timing
                            if isinstance(chunk.timing, dict)
                            else {}
                        ),
                        "speculative_tts_cache": True,
                        "speculation_generation_id": entry.generation_id,
                    }
                if terminal:
                    break

            if emitted == 0 and error:
                stream_log(
                    "gateway-live-speculative-tts",
                    "provider",
                    "speculative_tts_cache_fallback",
                    generation_id=entry.generation_id,
                    error=error,
                )
                yield from _locked_provider_stream(
                    self._provider,
                    text=text,
                    speaker=speaker,
                    language=language,
                    kwargs=kwargs,
                )
                replay_completed = True
                return

            if claim.remainder_text:
                yield from _locked_provider_stream(
                    self._provider,
                    text=claim.remainder_text,
                    speaker=speaker,
                    language=language,
                    kwargs=kwargs,
                )

            replay_completed = True
            stream_log(
                "gateway-live-speculative-tts",
                "provider",
                "speculative_tts_cache_replayed",
                generation_id=entry.generation_id,
                emitted_chunk_count=emitted,
                completed=entry.completed,
                cancelled=entry.cancelled,
                error=entry.error,
                prefix_match=bool(claim.remainder_text),
                remainder_text_length=len(claim.remainder_text),
            )
        finally:
            if not replay_completed:
                with entry.condition:
                    background_active = (
                        not entry.completed and not entry.cancelled
                    )
                    if background_active:
                        entry.cancelled = True
                        entry.condition.notify_all()
                if background_active:
                    stream_log(
                        "gateway-live-speculative-tts",
                        "provider",
                        "speculative_tts_replay_consumer_cancelled",
                        generation_id=entry.generation_id,
                        emitted_chunk_count=emitted,
                    )


def clear_speculative_tts_cache() -> None:
    with _CACHE_LOCK:
        entries = list(_ENTRIES.values())
        _ENTRIES.clear()
    for entry in entries:
        with entry.condition:
            entry.cancelled = True
            entry.condition.notify_all()


def speculative_tts_cache_snapshot() -> list[dict[str, Any]]:
    with _CACHE_LOCK:
        _prune_entries_locked()
        return [
            {
                "generation_id": entry.generation_id,
                "accepted": entry.accepted,
                "claimed": entry.claimed,
                "completed": entry.completed,
                "cancelled": entry.cancelled,
                "error": entry.error,
                "chunk_count": len(entry.chunks),
                "text_length": len(entry.text),
            }
            for entry in _ENTRIES.values()
        ]


def _stream_kwargs(request: TtsStreamRequest, provider: Any) -> dict[str, Any]:
    performance = apply_performance_plan_to_provider(
        provider,
        request.delivery_plan,
    )
    kwargs: dict[str, Any] = {
        "chunk_size": request.chunk_size,
        "temperature": request.temperature,
        "top_k": request.top_k,
        "top_p": request.top_p,
        "repetition_penalty": request.repetition_penalty,
        "append_silence": request.append_silence,
        "non_streaming_mode": False,
    }
    if request.max_new_tokens is not None:
        kwargs["max_new_tokens"] = request.max_new_tokens
    if request.parity_mode is not None:
        kwargs["parity_mode"] = request.parity_mode
    kwargs.update(performance.provider_kwargs)
    return kwargs


def _locked_provider_stream(
    provider: Any,
    *,
    text: str,
    speaker: str | None,
    language: str,
    kwargs: dict[str, Any],
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[tuple[Any, int, Any]]:
    with _PROVIDER_GENERATION_LOCK:
        if should_stop is not None and should_stop():
            return
        stream = provider.generate_audio_stream(
            text=text,
            speaker=speaker,
            language=language,
            **kwargs,
        )
        for chunk in stream:
            if should_stop is not None and should_stop():
                return
            yield chunk


def _start_prefetch(
    generation_id: str,
    request: TtsStreamRequest,
    provider: Any,
) -> _SpeculativeTtsEntry:
    text = _normalized_text(remove_emojis(request.text or ""))
    if not text:
        raise HTTPException(status_code=422, detail="text_required")
    speaker = _normalized_speaker(request.speaker)
    language = _normalized_language(request.language or "en")
    kwargs = _stream_kwargs(request, provider)
    stable_kwargs = _stable_kwargs(kwargs)
    key = _stream_key(text, speaker, language, stable_kwargs)
    entry = _SpeculativeTtsEntry(
        generation_id=generation_id,
        key=key,
        created_at=time.time(),
        text=text,
        speaker=speaker,
        language=language,
        stable_kwargs=stable_kwargs,
    )
    with _CACHE_LOCK:
        _prune_entries_locked()
        previous = _ENTRIES.pop(generation_id, None)
        _ENTRIES[generation_id] = entry
        _prune_entries_locked()
    if previous is not None:
        with previous.condition:
            previous.cancelled = True
            previous.condition.notify_all()

    def stopped() -> bool:
        with entry.condition:
            return entry.cancelled

    def produce() -> None:
        started = time.perf_counter()
        try:
            stream = _locked_provider_stream(
                provider,
                text=text,
                speaker=request.speaker,
                language=request.language or "en",
                kwargs=kwargs,
                should_stop=stopped,
            )
            for audio_chunk, sample_rate, timing in stream:
                pcm_bytes = audio_chunk_to_pcm16_bytes(audio_chunk)
                if not pcm_bytes:
                    continue
                with entry.condition:
                    if entry.cancelled:
                        break
                    entry.chunks.append(
                        _CachedPcmChunk(
                            pcm_bytes=pcm_bytes,
                            sample_rate=int(sample_rate or 24_000),
                            timing=timing,
                        )
                    )
                    entry.condition.notify_all()
        except Exception as exc:  # noqa: BLE001 - private speculative work
            with entry.condition:
                entry.error = str(exc) or type(exc).__name__
                entry.condition.notify_all()
        finally:
            with entry.condition:
                entry.completed = True
                entry.condition.notify_all()
            stream_log(
                "gateway-live-speculative-tts",
                "provider",
                "speculative_tts_prefetch_finished",
                generation_id=generation_id,
                chunk_count=len(entry.chunks),
                accepted=entry.accepted,
                claimed=entry.claimed,
                cancelled=entry.cancelled,
                error=entry.error,
                elapsed_ms=round(
                    (time.perf_counter() - started) * 1000.0,
                    3,
                ),
            )

    threading.Thread(
        target=produce,
        name=f"omnix-spec-tts-{generation_id[-20:]}",
        daemon=True,
    ).start()
    return entry


def _accept_entry(generation_id: str) -> _SpeculativeTtsEntry:
    with _CACHE_LOCK:
        _prune_entries_locked()
        entry = _ENTRIES.get(generation_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail="speculative_tts_not_found",
            )
        entry.accepted = True
        return entry


def _cancel_entry(generation_id: str) -> bool:
    with _CACHE_LOCK:
        entry = _ENTRIES.pop(generation_id, None)
    if entry is None:
        return False
    with entry.condition:
        entry.cancelled = True
        entry.condition.notify_all()
    return True


def _claim_entry(
    text: str,
    speaker: str | None,
    language: str,
    kwargs: dict[str, Any],
) -> _CacheClaim | None:
    actual_text = _normalized_text(text)
    actual_speaker = _normalized_speaker(speaker)
    actual_language = _normalized_language(language)
    actual_kwargs = _stable_kwargs(kwargs)
    with _CACHE_LOCK:
        _prune_entries_locked()
        matches: list[tuple[int, float, _SpeculativeTtsEntry, str]] = []
        for entry in _ENTRIES.values():
            if (
                not entry.accepted
                or entry.claimed
                or entry.cancelled
                or entry.error is not None
                or entry.speaker != actual_speaker
                or entry.language != actual_language
                or entry.stable_kwargs != actual_kwargs
            ):
                continue
            remainder = _prefix_remainder(entry.text, actual_text)
            if remainder is None:
                continue
            matches.append(
                (len(entry.text), entry.created_at, entry, remainder)
            )
        if not matches:
            return None
        _, _, entry, remainder = max(
            matches,
            key=lambda item: (item[0], item[1]),
        )
        entry.claimed = True
        return _CacheClaim(entry=entry, remainder_text=remainder)


def _prefix_remainder(cached_text: str, actual_text: str) -> str | None:
    if actual_text == cached_text:
        return ""
    if not actual_text.startswith(cached_text):
        return None
    boundary = actual_text[len(cached_text) : len(cached_text) + 1]
    if cached_text[-1:].isalnum() and boundary.isalnum():
        return None
    remainder = actual_text[len(cached_text) :].strip()
    if not remainder or _ONLY_PUNCTUATION.fullmatch(remainder):
        return ""
    return remainder.lstrip(" ,;:—–-").strip()


def _normalized_text(text: str) -> str:
    return " ".join((text or "").split())


def _normalized_speaker(speaker: str | None) -> str:
    return (speaker or "").strip()


def _normalized_language(language: str | None) -> str:
    return (language or "en").strip().casefold()


def _stable_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe(value)
        for key, value in kwargs.items()
        if key in _CACHE_KEY_KWARGS
    }


def _stream_key(
    text: str,
    speaker: str,
    language: str,
    stable_kwargs: dict[str, Any],
) -> str:
    payload = {
        "text": text,
        "speaker": speaker,
        "language": language,
        "kwargs": stable_kwargs,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump(mode="json"))
    return repr(value)


def _prune_entries_locked() -> None:
    cutoff = time.time() - _CACHE_TTL_SECONDS
    expired = [
        generation_id
        for generation_id, entry in _ENTRIES.items()
        if entry.created_at < cutoff
    ]
    for generation_id in expired:
        entry = _ENTRIES.pop(generation_id, None)
        if entry is not None:
            with entry.condition:
                entry.cancelled = True
                entry.condition.notify_all()
    if len(_ENTRIES) <= _MAX_CACHE_ENTRIES:
        return
    oldest = sorted(_ENTRIES.values(), key=lambda item: item.created_at)
    for entry in oldest[: len(_ENTRIES) - _MAX_CACHE_ENTRIES]:
        _ENTRIES.pop(entry.generation_id, None)
        with entry.condition:
            entry.cancelled = True
            entry.condition.notify_all()


def register_live_speculative_tts_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post("/api/live/speculation/tts-prefetch", include_in_schema=False)
    async def prefetch_speculative_tts(
        payload: SpeculativeTtsPrefetchRequest,
    ) -> dict[str, Any]:
        provider = shared.get_tts_provider()
        if provider is None or not hasattr(
            provider,
            "generate_audio_stream",
        ):
            raise HTTPException(
                status_code=503,
                detail="tts_provider_unavailable",
            )
        entry = _start_prefetch(
            payload.generation_id,
            payload.request,
            provider,
        )
        stream_log(
            "gateway-live-speculative-tts",
            "runtime",
            "speculative_tts_prefetch_started",
            generation_id=payload.generation_id,
            text_length=len(payload.request.text or ""),
            speaker=payload.request.speaker,
        )
        return {
            "ok": True,
            "generation_id": entry.generation_id,
            "status": "generating",
        }

    @app.post(
        "/api/live/speculation/tts-prefetch/{generation_id}/accept",
        include_in_schema=False,
    )
    async def accept_speculative_tts(generation_id: str) -> dict[str, Any]:
        entry = _accept_entry(generation_id)
        with entry.condition:
            buffered = len(entry.chunks)
            completed = entry.completed
        stream_log(
            "gateway-live-speculative-tts",
            "runtime",
            "speculative_tts_prefetch_accepted",
            generation_id=generation_id,
            buffered_chunk_count=buffered,
            completed=completed,
        )
        return {
            "ok": True,
            "generation_id": generation_id,
            "buffered_chunk_count": buffered,
            "completed": completed,
        }

    @app.post(
        "/api/live/speculation/tts-prefetch/{generation_id}/cancel",
        include_in_schema=False,
    )
    async def cancel_speculative_tts(generation_id: str) -> dict[str, Any]:
        cancelled = _cancel_entry(generation_id)
        return {
            "ok": True,
            "generation_id": generation_id,
            "cancelled": cancelled,
        }


def install_live_speculative_tts_prefetch_hook() -> None:
    """Install speculative routes and wrap the live-call provider lookup."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_get_provider = tts_live_call_websocket.get_tts_provider

    @wraps(original_get_provider)
    def prefetched_provider() -> Any:
        provider = original_get_provider()
        if provider is None or isinstance(
            provider,
            _PrefetchingProviderProxy,
        ):
            return provider
        return _PrefetchingProviderProxy(provider)

    tts_live_call_websocket.get_tts_provider = prefetched_provider

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        is_gateway = kwargs.get("title") == "Omnix Web Gateway"
        if is_gateway or (args and args[0] == "Omnix Web Gateway"):
            register_live_speculative_tts_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


__all__ = [
    "SpeculativeTtsPrefetchRequest",
    "clear_speculative_tts_cache",
    "install_live_speculative_tts_prefetch_hook",
    "register_live_speculative_tts_routes",
    "speculative_tts_cache_snapshot",
]
