"""Unbuffered control-plane handshake for live LLM speculation.

The original combined POST+SSE endpoint remains available for compatibility. This
module separates the tiny generation-allocation response from the streaming body
so browser and development proxies cannot delay the generation id until provider
text is available.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.chat import ChatSessionStore, default_chat_store

from . import live_chat_speculation as speculation_runtime
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_live_chat_speculation_handshake_registered"
_HANDSHAKE_RUNTIME: dict[str, tuple[ChatSessionStore, Any]] = {}
_STREAM_STARTED: set[str] = set()


def clear_live_speculation_handshake_state() -> None:
    """Clear transient handshake state for focused tests."""

    with speculation_runtime._SPECULATION_LOCK:
        _HANDSHAKE_RUNTIME.clear()
        _STREAM_STARTED.clear()


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

        generation_id = f"spec-{uuid.uuid4().hex}"
        pending = speculation_runtime._Speculation(
            generation_id=generation_id,
            session_id=session_id,
            candidate_text=request.content.strip(),
            provider_id=request.provider_id or session.provider_id,
            model_id=request.model_id or session.model_id,
            segment_id=request.segment_id,
            source_sequence=request.source_sequence,
            created_at=time.time(),
        )
        with speculation_runtime._SPECULATION_LOCK:
            speculation_runtime._prune_speculations()
            _prune_handshake_state_locked()
            speculation_runtime._SPECULATIONS[generation_id] = pending
            _HANDSHAKE_RUNTIME[generation_id] = (store, session)

        total_ms = (time.perf_counter() - started) * 1000.0
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_handshake_ready",
            generation_id=generation_id,
            cache_hit=cache_hit,
            session_load_ms=round(session_load_ms, 3),
            total_ms=round(total_ms, 3),
        )
        return {
            "ok": True,
            "generation_id": generation_id,
            "segment_id": request.segment_id,
            "source_sequence": request.source_sequence,
            "provider_id": pending.provider_id,
            "model_id": pending.model_id,
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
            runtime = _HANDSHAKE_RUNTIME.get(generation_id)
            if pending is None or pending.session_id != session_id:
                raise HTTPException(status_code=404, detail="speculation_not_found")
            if generation_id in _STREAM_STARTED:
                raise HTTPException(
                    status_code=409,
                    detail="speculation_stream_already_started",
                )
            if runtime is None:
                raise HTTPException(
                    status_code=409,
                    detail="speculation_handshake_expired",
                )
            _STREAM_STARTED.add(generation_id)

        store, session = runtime

        def generate() -> Iterator[str]:
            try:
                yield from speculation_runtime._generate_side_effect_free(
                    store,
                    session,
                    pending,
                )
            except Exception as exc:  # noqa: BLE001 - normalized into private stream
                message = str(exc) or "Speculative generation failed."
                with speculation_runtime._SPECULATION_LOCK:
                    pending.error = message
                    pending.completed = True
                yield speculation_runtime._sse(
                    {
                        "type": "error",
                        "generation_id": generation_id,
                        "message": message,
                    }
                )
            finally:
                with speculation_runtime._SPECULATION_LOCK:
                    _HANDSHAKE_RUNTIME.pop(generation_id, None)
                yield speculation_runtime._sse(
                    {"type": "done", "generation_id": generation_id}
                )

        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_stream_attached",
            generation_id=generation_id,
        )
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-transform",
                "X-Accel-Buffering": "no",
            },
        )


def _prune_handshake_state_locked() -> None:
    active_ids = set(speculation_runtime._SPECULATIONS)
    for generation_id in list(_HANDSHAKE_RUNTIME):
        if generation_id not in active_ids:
            _HANDSHAKE_RUNTIME.pop(generation_id, None)
            _STREAM_STARTED.discard(generation_id)


__all__ = [
    "clear_live_speculation_handshake_state",
    "register_live_chat_speculation_handshake_routes",
]
