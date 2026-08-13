"""Eager, buffered control-plane handshake for live LLM speculation.

The legacy combined POST+SSE endpoint remains available for compatibility. This
module separates generation allocation from stream subscription and starts the
side-effect-free provider request as soon as the allocation succeeds. Generated
SSE frames are held in a bounded per-generation buffer until the browser attaches.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.chat import ChatSessionStore, default_chat_store

from . import live_chat_speculation as speculation_runtime
from .live_voice_execution_lane import resolve_live_voice_chat_route
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_live_chat_speculation_handshake_registered"
_MAX_BUFFERED_EVENTS = 256
_MAX_BUFFERED_BYTES = 256 * 1024


class _SpeculationBufferLimitExceeded(RuntimeError):
    """Raised when an unattached speculative stream exceeds its private buffer."""


@dataclass
class _HandshakeGeneration:
    store: ChatSessionStore
    session: Any
    created_at: float = field(default_factory=time.time)
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )
    events: deque[str] = field(default_factory=deque)
    buffered_bytes: int = 0
    stream_started: bool = False
    completed: bool = False
    terminal_emitted: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None


_HANDSHAKE_GENERATIONS: dict[str, _HandshakeGeneration] = {}
_STREAM_STARTED: set[str] = set()


def clear_live_speculation_handshake_state() -> None:
    """Cancel and clear transient handshake state for focused tests."""

    with speculation_runtime._SPECULATION_LOCK:
        generations = list(_HANDSHAKE_GENERATIONS.values())
        _HANDSHAKE_GENERATIONS.clear()
        _STREAM_STARTED.clear()
    for generation in generations:
        generation.cancel_event.set()
        with generation.condition:
            generation.completed = True
            generation.condition.notify_all()


def register_live_chat_speculation_handshake_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/live/speculation/sessions/{session_id}/start",
        include_in_schema=False,
    )
    async def start_live_speculation(
        session_id: str,
        request: speculation_runtime.LiveSpeculationRequest,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if not speculation_runtime.transcript_is_speculation_safe(request.content):
            raise HTTPException(
                status_code=409,
                detail="speculation_transcript_not_stable",
            )

        store = chat_store_factory()
        session, cache_hit, session_load_ms = (
            await speculation_runtime._resolve_speculation_session(store, session_id)
        )
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")

        provider_id, model_id, execution_lane = resolve_live_voice_chat_route(
            request.provider_id or session.provider_id,
            request.model_id or session.model_id,
        )
        generation_id = f"spec-{uuid.uuid4().hex}"
        pending = speculation_runtime._Speculation(
            generation_id=generation_id,
            session_id=session_id,
            candidate_text=request.content.strip(),
            provider_id=provider_id,
            model_id=model_id,
            segment_id=request.segment_id,
            source_sequence=request.source_sequence,
            created_at=time.time(),
            execution_lane=execution_lane,
        )
        generation = _HandshakeGeneration(store=store, session=session)
        worker = threading.Thread(
            target=_run_generation,
            args=(pending, generation),
            name=f"omnix-live-speculation-{generation_id[-8:]}",
            daemon=True,
        )
        generation.worker = worker
        with speculation_runtime._SPECULATION_LOCK:
            speculation_runtime._prune_speculations()
            _prune_handshake_state_locked()
            speculation_runtime._SPECULATIONS[generation_id] = pending
            _HANDSHAKE_GENERATIONS[generation_id] = generation
        worker.start()

        total_ms = (time.perf_counter() - started) * 1000.0
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_handshake_ready",
            generation_id=generation_id,
            cache_hit=cache_hit,
            session_load_ms=round(session_load_ms, 3),
            total_ms=round(total_ms, 3),
            generation_started=True,
            execution_lane=execution_lane,
            provider_id=provider_id,
            model_id=model_id,
            max_buffered_events=_MAX_BUFFERED_EVENTS,
            max_buffered_bytes=_MAX_BUFFERED_BYTES,
        )
        return {
            "ok": True,
            "generation_id": generation_id,
            "segment_id": request.segment_id,
            "source_sequence": request.source_sequence,
            "provider_id": pending.provider_id,
            "model_id": pending.model_id,
            "execution_lane": pending.execution_lane,
        }

    @app.post(
        "/api/live/speculation/sessions/{session_id}/{generation_id}/stream",
        include_in_schema=False,
    )
    async def stream_started_live_speculation(
        session_id: str,
        generation_id: str,
    ) -> StreamingResponse:
        with speculation_runtime._SPECULATION_LOCK:
            speculation_runtime._prune_speculations()
            _prune_handshake_state_locked()
            pending = speculation_runtime._SPECULATIONS.get(generation_id)
            generation = _HANDSHAKE_GENERATIONS.get(generation_id)
            if pending is None or pending.session_id != session_id:
                raise HTTPException(status_code=404, detail="speculation_not_found")
            if generation_id in _STREAM_STARTED:
                raise HTTPException(
                    status_code=409,
                    detail="speculation_stream_already_started",
                )
            if generation is None:
                raise HTTPException(
                    status_code=409,
                    detail="speculation_handshake_expired",
                )
            generation.stream_started = True
            _STREAM_STARTED.add(generation_id)

        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_stream_attached",
            generation_id=generation_id,
            buffered_event_count=len(generation.events),
            buffered_bytes=generation.buffered_bytes,
            generation_completed=generation.completed,
            execution_lane=pending.execution_lane,
            attach_delay_ms=round(
                max(0.0, (time.time() - generation.created_at) * 1000.0),
                3,
            ),
        )
        return StreamingResponse(
            _subscribe_generation(generation_id, pending, generation),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-transform",
                "X-Accel-Buffering": "no",
                "X-Omnix-Live-Execution-Lane": pending.execution_lane,
            },
        )

    @app.post(
        "/api/live/speculation/sessions/{session_id}/{generation_id}/cancel",
        include_in_schema=False,
    )
    async def cancel_started_live_speculation(
        session_id: str,
        generation_id: str,
    ) -> dict[str, Any]:
        with speculation_runtime._SPECULATION_LOCK:
            speculation_runtime._prune_speculations()
            _prune_handshake_state_locked()
            pending = speculation_runtime._SPECULATIONS.get(generation_id)
            generation = _HANDSHAKE_GENERATIONS.get(generation_id)
            if pending is None or pending.session_id != session_id:
                raise HTTPException(status_code=404, detail="speculation_not_found")

        already_completed = pending.completed
        if generation is not None and not already_completed:
            generation.cancel_event.set()
            _finish_with_error(
                pending,
                generation,
                code="speculation_cancelled",
                message="Speculative generation cancelled.",
            )
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_cancelled",
            generation_id=generation_id,
            already_completed=already_completed,
            stream_started=bool(generation and generation.stream_started),
            execution_lane=pending.execution_lane,
        )
        return {
            "ok": True,
            "generation_id": generation_id,
            "already_completed": already_completed,
        }


def _run_generation(
    pending: Any,
    generation: _HandshakeGeneration,
) -> None:
    generation_started = time.perf_counter()
    stream_log(
        "gateway-live-chat-speculation",
        "runtime",
        "live_chat_speculation_generation_started",
        generation_id=pending.generation_id,
        eager=True,
        execution_lane=getattr(pending, "execution_lane", "session"),
    )
    try:
        for event in speculation_runtime._generate_side_effect_free(
            generation.store,
            generation.session,
            pending,
            cancel_event=generation.cancel_event,
        ):
            if generation.cancel_event.is_set():
                return
            _append_event(generation, event)
        if generation.cancel_event.is_set():
            return
        _finish_success(pending, generation)
    except _SpeculationBufferLimitExceeded:
        generation.cancel_event.set()
        _finish_with_error(
            pending,
            generation,
            code="speculation_buffer_limit_exceeded",
            message="Speculative generation exceeded its private buffer limit.",
        )
    except Exception as exc:  # noqa: BLE001 - normalized into private stream
        message = str(exc) or "Speculative generation failed."
        _finish_with_error(
            pending,
            generation,
            code="speculation_generation_failed",
            message=message,
        )
    finally:
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_generation_finished",
            generation_id=pending.generation_id,
            elapsed_ms=round(
                (time.perf_counter() - generation_started) * 1000.0,
                3,
            ),
            completed=pending.completed,
            cancelled=generation.cancel_event.is_set(),
            failed=bool(pending.error),
            stream_started=generation.stream_started,
            execution_lane=getattr(pending, "execution_lane", "session"),
        )


def _append_event(generation: _HandshakeGeneration, event: str) -> None:
    event_bytes = len(event.encode("utf-8"))
    with generation.condition:
        if generation.terminal_emitted or generation.cancel_event.is_set():
            return
        if (
            len(generation.events) >= _MAX_BUFFERED_EVENTS
            or generation.buffered_bytes + event_bytes > _MAX_BUFFERED_BYTES
        ):
            raise _SpeculationBufferLimitExceeded
        generation.events.append(event)
        generation.buffered_bytes += event_bytes
        generation.condition.notify_all()


def _finish_success(pending: Any, generation: _HandshakeGeneration) -> None:
    with generation.condition:
        if generation.terminal_emitted:
            return
        pending.completed = True
        generation.events.append(
            speculation_runtime._sse(
                {"type": "done", "generation_id": pending.generation_id}
            )
        )
        generation.completed = True
        generation.terminal_emitted = True
        generation.condition.notify_all()


def _finish_with_error(
    pending: Any,
    generation: _HandshakeGeneration,
    *,
    code: str,
    message: str,
) -> None:
    with generation.condition:
        if generation.terminal_emitted:
            return
        pending.error = code
        pending.completed = True
        generation.events.clear()
        generation.buffered_bytes = 0
        error_event = speculation_runtime._sse(
            {
                "type": "error",
                "generation_id": pending.generation_id,
                "code": code,
                "message": message,
            }
        )
        done_event = speculation_runtime._sse(
            {"type": "done", "generation_id": pending.generation_id}
        )
        generation.events.extend((error_event, done_event))
        generation.buffered_bytes = len(error_event.encode("utf-8")) + len(
            done_event.encode("utf-8")
        )
        generation.completed = True
        generation.terminal_emitted = True
        generation.condition.notify_all()


def _subscribe_generation(
    generation_id: str,
    pending: Any,
    generation: _HandshakeGeneration,
) -> Iterator[str]:
    try:
        while True:
            event = None
            with generation.condition:
                while not generation.events and not generation.completed:
                    generation.condition.wait(timeout=0.5)
                if generation.events:
                    event = generation.events.popleft()
                    generation.buffered_bytes = max(
                        0,
                        generation.buffered_bytes - len(event.encode("utf-8")),
                    )
                elif generation.completed:
                    break
            if event is not None:
                yield event
    finally:
        if not generation.completed:
            generation.cancel_event.set()
            _finish_with_error(
                pending,
                generation,
                code="speculation_stream_detached",
                message="Speculative generation stream detached.",
            )
        with speculation_runtime._SPECULATION_LOCK:
            current = _HANDSHAKE_GENERATIONS.get(generation_id)
            if current is generation:
                _HANDSHAKE_GENERATIONS.pop(generation_id, None)


def _prune_handshake_state_locked() -> None:
    active_ids = set(speculation_runtime._SPECULATIONS)
    for generation_id in list(_STREAM_STARTED):
        if generation_id not in active_ids:
            _STREAM_STARTED.discard(generation_id)
    expired = [
        (generation_id, generation)
        for generation_id, generation in _HANDSHAKE_GENERATIONS.items()
        if generation_id not in active_ids
    ]
    for generation_id, generation in expired:
        _HANDSHAKE_GENERATIONS.pop(generation_id, None)
        _STREAM_STARTED.discard(generation_id)
        generation.cancel_event.set()
        with generation.condition:
            generation.completed = True
            generation.condition.notify_all()


__all__ = [
    "clear_live_speculation_handshake_state",
    "register_live_chat_speculation_handshake_routes",
]
