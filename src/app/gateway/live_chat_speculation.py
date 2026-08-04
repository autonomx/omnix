"""Side-effect-free LLM speculation for stable live-STT partials."""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import shared
from app.chat import (
    ChatMessage,
    ChatSessionStore,
    SendChatMessageRequest,
    default_chat_store,
)
from app.chat.store import _model_key, _provider_key
from app.gateway.live_chat_low_latency_stream import LowLatencyTextChunker
from app.gateway.live_chat_prompt_fast_path import build_live_provider_prompt
from app.providers import ChatMessage as ProviderMessage

_ROUTE_SENTINEL = "_omnix_live_chat_speculation_registered"
_SPECULATION_TTL_SECONDS = 90.0
_SPECULATION_ACCEPT_WAIT_SECONDS = 5.0
_MAX_SPECULATIONS = 64
_WORD_PATTERN = re.compile(r"[\w]+(?:['’][\w]+)?", re.UNICODE)
_UNRESOLVED_CORRECTION_PATTERN = re.compile(
    r"(?:^|\s)(?:uh+|um+|erm+|wait|sorry|actually|correction|no[,. ]+i mean)(?:\s|$)",
    re.IGNORECASE,
)


class LiveSpeculationRequest(BaseModel):
    content: str = Field(min_length=2, max_length=8_000)
    provider_id: str | None = None
    model_id: str | None = None
    segment_id: str = Field(min_length=1, max_length=180)
    source_sequence: int = Field(ge=0)


class LiveSpeculationAcceptRequest(BaseModel):
    final_text: str = Field(min_length=1, max_length=8_000)
    provider_id: str | None = None
    model_id: str | None = None
    agent_mode: bool = False
    dry_run: bool = False
    research_mode: str | None = None
    user_turn_id: str | None = Field(default=None, min_length=1, max_length=160)
    speech_segment_id: str | None = Field(default=None, min_length=1, max_length=160)
    live_voice_turn_id: str | None = Field(default=None, min_length=1, max_length=160)


@dataclass
class _Speculation:
    generation_id: str
    session_id: str
    candidate_text: str
    provider_id: str | None
    model_id: str | None
    segment_id: str
    source_sequence: int
    created_at: float
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    error: str | None = None
    accepting: bool = False
    accept_error: str | None = None
    accepted_payload: dict[str, Any] | None = None
    accept_event: threading.Event = field(default_factory=threading.Event, repr=False)


_SPECULATIONS: dict[str, _Speculation] = {}
_SPECULATION_LOCK = threading.RLock()


def normalized_transcript_words(text: str) -> tuple[str, ...]:
    return tuple(token.casefold().replace("’", "'") for token in _WORD_PATTERN.findall(text))


def transcript_is_speculation_safe(text: str) -> bool:
    words = normalized_transcript_words(text)
    return len(words) >= 2 and _UNRESOLVED_CORRECTION_PATTERN.search(text) is None


def transcripts_are_compatible(candidate: str, final: str) -> bool:
    return (
        transcript_is_speculation_safe(candidate)
        and normalized_transcript_words(candidate) == normalized_transcript_words(final)
    )


def speculation_accept_request_is_compatible(
    speculation: _Speculation,
    request: LiveSpeculationAcceptRequest,
) -> bool:
    if request.agent_mode or request.dry_run or request.research_mode:
        return False
    if request.provider_id and request.provider_id != speculation.provider_id:
        return False
    if request.model_id and request.model_id != speculation.model_id:
        return False
    return transcripts_are_compatible(speculation.candidate_text, request.final_text)


def register_live_chat_speculation_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/live/speculation/sessions/{session_id}/stream",
        include_in_schema=False,
    )
    async def stream_live_speculation(
        session_id: str,
        request: LiveSpeculationRequest,
    ) -> StreamingResponse:
        if not transcript_is_speculation_safe(request.content):
            raise HTTPException(status_code=409, detail="speculation_transcript_not_stable")
        store = chat_store_factory()
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        generation_id = f"spec-{uuid.uuid4().hex}"
        speculation = _Speculation(
            generation_id=generation_id,
            session_id=session_id,
            candidate_text=request.content.strip(),
            provider_id=request.provider_id or session.provider_id,
            model_id=request.model_id or session.model_id,
            segment_id=request.segment_id,
            source_sequence=request.source_sequence,
            created_at=time.time(),
        )
        with _SPECULATION_LOCK:
            _prune_speculations()
            _SPECULATIONS[generation_id] = speculation

        def generate() -> Iterator[str]:
            yield _sse({
                "type": "speculation_started",
                "generation_id": generation_id,
                "segment_id": request.segment_id,
                "source_sequence": request.source_sequence,
                "provider_id": speculation.provider_id,
                "model_id": speculation.model_id,
            })
            try:
                yield from _generate_side_effect_free(store, session, speculation)
            except Exception as exc:  # noqa: BLE001 - normalized into private speculative stream
                message = str(exc) or "Speculative generation failed."
                with _SPECULATION_LOCK:
                    speculation.error = message
                    speculation.completed = True
                yield _sse({"type": "error", "generation_id": generation_id, "message": message})
            finally:
                yield _sse({"type": "done", "generation_id": generation_id})

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post(
        "/api/live/speculation/sessions/{session_id}/{generation_id}/accept",
        include_in_schema=False,
    )
    async def accept_live_speculation(
        session_id: str,
        generation_id: str,
        request: LiveSpeculationAcceptRequest,
    ) -> dict[str, Any]:
        owns_accept = False
        wait_event: threading.Event | None = None
        with _SPECULATION_LOCK:
            _prune_speculations()
            speculation = _SPECULATIONS.get(generation_id)
            if speculation is None or speculation.session_id != session_id:
                raise HTTPException(status_code=404, detail="speculation_not_found")
            if not speculation.completed:
                raise HTTPException(status_code=409, detail="speculation_not_complete")
            if speculation.error:
                raise HTTPException(status_code=409, detail="speculation_failed")
            if not speculation_accept_request_is_compatible(speculation, request):
                raise HTTPException(status_code=409, detail="speculation_request_mismatch")
            if speculation.accepted_payload is not None:
                return dict(speculation.accepted_payload)
            if speculation.accepting:
                wait_event = speculation.accept_event
            else:
                speculation.accepting = True
                speculation.accept_error = None
                speculation.accept_event.clear()
                owns_accept = True

        if not owns_accept:
            assert wait_event is not None
            completed = await asyncio.to_thread(
                wait_event.wait,
                _SPECULATION_ACCEPT_WAIT_SECONDS,
            )
            if not completed:
                raise HTTPException(status_code=409, detail="speculation_accept_in_progress")
            with _SPECULATION_LOCK:
                if speculation.accepted_payload is not None:
                    return dict(speculation.accepted_payload)
                detail = speculation.accept_error or "speculation_accept_failed"
            raise HTTPException(status_code=409, detail=detail)

        try:
            accepted_request = _accepted_chat_request(
                request,
                speculation=speculation,
                generation_id=generation_id,
            )
            store = chat_store_factory()
            appended = store.begin_user_message(session_id, accepted_request)
            if appended is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            _, user_message = appended
            completed_session = store.complete_streamed_reply(
                session_id,
                user_message.id,
                speculation.content,
                {
                    **speculation.metadata,
                    "generation_status": "completed",
                    "speculative_generation": True,
                    "speculation_generation_id": generation_id,
                    "speculation_candidate_words": len(
                        normalized_transcript_words(speculation.candidate_text)
                    ),
                    "user_turn_id": accepted_request.user_turn_id,
                    "speech_segment_id": accepted_request.speech_segment_id,
                },
            )
            if completed_session is None:
                raise HTTPException(status_code=409, detail="speculation_accept_failed")
            payload = {
                "ok": True,
                "generation_id": generation_id,
                "content": speculation.content,
                "user_turn_id": accepted_request.user_turn_id,
                "speech_segment_id": accepted_request.speech_segment_id,
                "user_message": user_message.model_dump(mode="json"),
                "session": completed_session.model_dump(mode="json"),
            }
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else "speculation_accept_failed"
            with _SPECULATION_LOCK:
                speculation.accepting = False
                speculation.accept_error = str(detail)
                speculation.accept_event.set()
            raise
        with _SPECULATION_LOCK:
            speculation.accepted_payload = payload
            speculation.accepting = False
            speculation.accept_error = None
            speculation.accept_event.set()
        return payload


def _accepted_chat_request(
    request: LiveSpeculationAcceptRequest,
    *,
    speculation: _Speculation,
    generation_id: str,
) -> SendChatMessageRequest:
    payload: dict[str, Any] = {
        "content": request.final_text.strip(),
        "provider_id": speculation.provider_id,
        "model_id": speculation.model_id,
    }
    if request.user_turn_id:
        payload["user_turn_id"] = request.user_turn_id
    if request.speech_segment_id:
        payload["speech_segment_id"] = request.speech_segment_id
    if request.live_voice_turn_id:
        payload["live_voice_turn_id"] = request.live_voice_turn_id
    if not any(
        (request.user_turn_id, request.speech_segment_id, request.live_voice_turn_id)
    ):
        payload["user_turn_id"] = f"speculation-user:{generation_id}"[:160]
        payload["speech_segment_id"] = (
            f"speculation-segment:{speculation.segment_id}"[:160]
        )
    return SendChatMessageRequest.model_validate(payload)


def _generate_side_effect_free(
    store: ChatSessionStore,
    session: Any,
    speculation: _Speculation,
) -> Iterator[str]:
    provider = shared.get_provider(_provider_key(speculation.provider_id))
    if provider is None:
        raise RuntimeError("Chat provider is not available")
    user_message = ChatMessage(
        id=f"speculation-user-{speculation.generation_id}",
        role="user",
        content=speculation.candidate_text,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "speculative": True,
            "side_effects_allowed": False,
            "tools_allowed": False,
            "memory_writes_allowed": False,
        },
    )
    assembly, rendered = build_live_provider_prompt(store, session, user_message, [])
    messages = [ProviderMessage(role=item.role, content=item.content) for item in rendered.messages]
    response = provider.chat_completion(
        messages=messages,
        model=_model_key(speculation.model_id),
        stream=True,
    )
    chunker = LowLatencyTextChunker()
    full_text = ""
    for chunk in response:
        text = getattr(chunk, "content", "") or ""
        if not text:
            continue
        full_text += text
        for ready in chunker.push(text):
            yield _sse({
                "type": "text_chunk",
                "generation_id": speculation.generation_id,
                "text": ready,
            })
    remaining = chunker.flush()
    if remaining:
        yield _sse({
            "type": "text_chunk",
            "generation_id": speculation.generation_id,
            "text": remaining,
        })
    with _SPECULATION_LOCK:
        speculation.content = full_text.strip()
        speculation.metadata = {
            "provider_id": speculation.provider_id,
            "model_id": speculation.model_id,
            "resolved_model": speculation.model_id,
            "speculation_side_effects": "disabled",
            "speculation_tools": "disabled",
            "speculation_memory_writes": "disabled",
            "prompt_source_count": len(getattr(assembly, "sources", []) or []),
            "live_prompt_fast_path": bool(
                getattr(assembly, "diagnostics", {}).get("live_prompt_fast_path", {}).get("enabled")
            ),
        }
        speculation.completed = True
    yield _sse({
        "type": "complete",
        "generation_id": speculation.generation_id,
        "content": speculation.content,
        "metadata": speculation.metadata,
    })


def _prune_speculations() -> None:
    cutoff = time.time() - _SPECULATION_TTL_SECONDS
    expired = [key for key, value in _SPECULATIONS.items() if value.created_at < cutoff]
    for key in expired:
        _SPECULATIONS.pop(key, None)
    if len(_SPECULATIONS) <= _MAX_SPECULATIONS:
        return
    oldest = sorted(_SPECULATIONS.values(), key=lambda item: item.created_at)
    for item in oldest[: len(_SPECULATIONS) - _MAX_SPECULATIONS]:
        _SPECULATIONS.pop(item.generation_id, None)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"
