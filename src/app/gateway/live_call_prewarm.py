"""Best-effort live-call cold-path warm-up for local LLM and TTS providers."""
from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app import shared
from app.chat import ChatMessage, ChatSessionStore, default_chat_store
from app.chat.store import _model_key, _provider_key
from app.providers import ChatMessage as ProviderMessage
from app.providers.lmstudio_provider import LMStudioProvider
from app.shared import get_tts_provider

from .tts_stream_contract import audio_chunk_to_pcm16_bytes
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_live_call_prewarm_registered"
_PREWARM_TTL_SECONDS = 300.0
_PREWARM_WAIT_SECONDS = 8.0
_PREWARM_LOCK = threading.RLock()
_PREWARMED_AT: dict[str, float] = {}
_PREWARM_INFLIGHT: dict[str, threading.Event] = {}
_WARM_USER_CONTENT = "Reply with one short acknowledgement."


class LiveCallPrewarmRequest(BaseModel):
    speaker: str | None = Field(default=None, max_length=160)
    language: str = Field(default="English", min_length=1, max_length=40)


@dataclass(frozen=True)
class _WarmResult:
    status: str
    elapsed_ms: float
    detail: str | None = None
    prompt_message_count: int | None = None
    prompt_chars: int | None = None

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "detail": self.detail,
        }
        if self.prompt_message_count is not None:
            payload["prompt_message_count"] = self.prompt_message_count
        if self.prompt_chars is not None:
            payload["prompt_chars"] = self.prompt_chars
        return payload


def clear_live_call_prewarm_state() -> None:
    """Clear warm-up deduplication state for focused tests."""

    with _PREWARM_LOCK:
        waiting = list(_PREWARM_INFLIGHT.values())
        _PREWARM_INFLIGHT.clear()
        _PREWARMED_AT.clear()
    for event in waiting:
        event.set()


def register_live_call_prewarm_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
) -> None:
    """Register a side-effect-free warm-up endpoint used when a call opens."""

    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/live-call/sessions/{session_id}/prewarm",
        include_in_schema=False,
    )
    async def prewarm_live_call(
        session_id: str,
        request: LiveCallPrewarmRequest,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        store = chat_store_factory()
        session = await asyncio.to_thread(store.get_session, session_id)
        if session is None:
            return {
                "ok": False,
                "fully_warmed": False,
                "status": "session_not_found",
                "cached": False,
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            }

        key = _prewarm_key(
            session=session,
            speaker=request.speaker,
            language=request.language,
        )
        owner, cached, wait_event = _claim_prewarm(key)
        if cached:
            return {
                "ok": True,
                "fully_warmed": True,
                "status": "cached",
                "cached": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            }
        if not owner and wait_event is not None:
            await asyncio.to_thread(wait_event.wait, _PREWARM_WAIT_SECONDS)
            with _PREWARM_LOCK:
                completed = _recently_warmed_locked(key)
            return {
                "ok": completed,
                "fully_warmed": completed,
                "status": "shared" if completed else "wait_timeout",
                "cached": completed,
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            }

        stream_log(
            "gateway-live-call-prewarm",
            "runtime",
            "live_call_prewarm_started",
            session_id=session_id,
            provider_id=getattr(session, "provider_id", None),
            model_id=getattr(session, "model_id", None),
            interaction_mode=getattr(session, "interaction_mode", None),
            character_id=getattr(session, "character_id", None),
            character_profile_version=getattr(
                session,
                "character_profile_version",
                None,
            ),
            session_message_count=len(getattr(session, "messages", []) or []),
            speaker=request.speaker,
        )
        try:
            llm_result, tts_result = await asyncio.gather(
                asyncio.to_thread(_warm_llm, store, session),
                asyncio.to_thread(
                    _warm_tts,
                    request.speaker,
                    request.language,
                ),
            )
            results = (llm_result, tts_result)
            fully_warmed = all(result.status == "warmed" for result in results)
            no_failures = all(
                result.status in {"warmed", "unavailable"}
                for result in results
            )
            if fully_warmed:
                with _PREWARM_LOCK:
                    _PREWARMED_AT[key] = time.time()
            status = _combined_status(results, fully_warmed=fully_warmed)
            payload = {
                "ok": no_failures,
                "fully_warmed": fully_warmed,
                "status": status,
                "cached": False,
                "llm": llm_result.payload(),
                "tts": tts_result.payload(),
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            }
            stream_log(
                "gateway-live-call-prewarm",
                "runtime",
                "live_call_prewarm_completed",
                session_id=session_id,
                **payload,
            )
            return payload
        finally:
            _release_prewarm(key)


def _combined_status(
    results: tuple[_WarmResult, _WarmResult],
    *,
    fully_warmed: bool,
) -> str:
    if fully_warmed:
        return "completed"
    statuses = {result.status for result in results}
    if "warmed" in statuses:
        return "partial"
    if statuses == {"unavailable"}:
        return "unavailable"
    return "failed"


def _claim_prewarm(key: str) -> tuple[bool, bool, threading.Event | None]:
    with _PREWARM_LOCK:
        _prune_prewarm_locked()
        if _recently_warmed_locked(key):
            return False, True, None
        existing = _PREWARM_INFLIGHT.get(key)
        if existing is not None:
            return False, False, existing
        event = threading.Event()
        _PREWARM_INFLIGHT[key] = event
        return True, False, event


def _release_prewarm(key: str) -> None:
    with _PREWARM_LOCK:
        event = _PREWARM_INFLIGHT.pop(key, None)
    if event is not None:
        event.set()


def _recently_warmed_locked(key: str) -> bool:
    warmed_at = _PREWARMED_AT.get(key)
    return warmed_at is not None and time.time() - warmed_at <= _PREWARM_TTL_SECONDS


def _prune_prewarm_locked() -> None:
    cutoff = time.time() - _PREWARM_TTL_SECONDS
    for key, warmed_at in list(_PREWARMED_AT.items()):
        if warmed_at < cutoff:
            _PREWARMED_AT.pop(key, None)


def _prewarm_key(
    *,
    session: Any,
    speaker: str | None,
    language: str,
) -> str:
    return "|".join(
        (
            str(getattr(session, "id", "") or ""),
            str(getattr(session, "provider_id", "") or ""),
            str(getattr(session, "model_id", "") or ""),
            str(getattr(session, "interaction_mode", "") or ""),
            str(getattr(session, "character_id", "") or ""),
            str(getattr(session, "character_profile_version", "") or ""),
            str(getattr(session, "effective_identity_hash", "") or ""),
            str(getattr(session, "active_segment_id", "") or ""),
            str(getattr(session, "message_count", "") or ""),
            str(getattr(session, "updated_at", "") or ""),
            str(speaker or ""),
            language.casefold(),
        )
    )


def _warm_llm(store: Any, session: Any) -> _WarmResult:
    started = time.perf_counter()
    provider = shared.get_provider(_provider_key(getattr(session, "provider_id", None)))
    if provider is None or not hasattr(provider, "chat_completion"):
        return _WarmResult(
            status="unavailable",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            detail="chat_provider_unavailable",
        )

    response: Iterator[Any] | None = None
    prompt_messages: list[ProviderMessage] = []
    try:
        prompt_messages = _live_voice_warm_messages(store, session)
        # A session may retain a stale configured LM Studio model identifier.
        # Passing no explicit model lets the loaded-model resolver use the model
        # that is actually resident in LM Studio at call time.
        model = (
            None
            if isinstance(provider, LMStudioProvider)
            else _model_key(getattr(session, "model_id", None))
        )
        response = provider.chat_completion(
            messages=prompt_messages,
            model=model,
            stream=True,
            chat_template_kwargs={"enable_thinking": False},
        )
        for chunk in response:
            if str(getattr(chunk, "content", "") or "").strip():
                break
        return _WarmResult(
            status="warmed",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            prompt_message_count=len(prompt_messages),
            prompt_chars=sum(len(message.content) for message in prompt_messages),
        )
    except Exception as exc:  # noqa: BLE001 - warm-up must never block live calls.
        return _WarmResult(
            status="failed",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            detail=f"{type(exc).__name__}:{exc}",
            prompt_message_count=len(prompt_messages) or None,
            prompt_chars=(
                sum(len(message.content) for message in prompt_messages)
                if prompt_messages
                else None
            ),
        )
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            with suppress(Exception):
                close()


def _live_voice_warm_messages(store: Any, session: Any) -> list[ProviderMessage]:
    warm_message = ChatMessage(
        id=f"live-call-prewarm:{getattr(session, 'id', 'session')}",
        role="user",
        content=_WARM_USER_CONTENT,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "prewarm": True,
            "side_effects_allowed": False,
            "tools_allowed": False,
            "memory_writes_allowed": False,
            "user_turn_id": "voice-user-turn:live-call-prewarm",
            "speech_segment_id": "voice-segment:live-call-prewarm",
        },
    )
    builder = getattr(store, "build_provider_prompt", None)
    if not callable(builder):
        return [ProviderMessage(role="user", content=_WARM_USER_CONTENT)]
    _, rendered = builder(session, warm_message, [])
    return [
        ProviderMessage(role=message.role, content=message.content)
        for message in rendered.messages
    ]


def _warm_tts(speaker: str | None, language: str) -> _WarmResult:
    started = time.perf_counter()
    provider = get_tts_provider()
    if provider is None or not hasattr(provider, "generate_audio_stream"):
        return _WarmResult(
            status="unavailable",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            detail="tts_provider_unavailable",
        )

    provider_stream: Iterator[Any] | None = None
    try:
        provider_stream = provider.generate_audio_stream(
            text="Ready.",
            speaker=speaker,
            language=language,
            chunk_size=1,
            temperature=0.6,
            top_k=20,
            top_p=0.85,
            repetition_penalty=1.05,
            append_silence=False,
            max_new_tokens=12,
            parity_mode=False,
            non_streaming_mode=False,
        )
        first = next(provider_stream, None)
        if first is not None:
            audio_chunk = first[0] if isinstance(first, tuple) else first
            audio_chunk_to_pcm16_bytes(audio_chunk)
        return _WarmResult(
            status="warmed",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as exc:  # noqa: BLE001 - warm-up must never block live calls.
        return _WarmResult(
            status="failed",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            detail=f"{type(exc).__name__}:{exc}",
        )
    finally:
        close = getattr(provider_stream, "close", None)
        if callable(close):
            with suppress(Exception):
                close()


__all__ = [
    "LiveCallPrewarmRequest",
    "clear_live_call_prewarm_state",
    "register_live_call_prewarm_routes",
]