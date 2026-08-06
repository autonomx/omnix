"""Single-request eager SSE transport for live LLM speculation.

This route allocates the speculative generation and attaches its only consumer
before the worker begins. It removes the second browser request from the hot
path while retaining the existing JSON handshake routes as a compatibility
fallback.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.chat import ChatSessionStore, default_chat_store

from . import live_chat_speculation as speculation_runtime
from . import live_chat_speculation_handshake as handshake_runtime
from .tts_stream_diagnostics import stream_log

_ROUTE_SENTINEL = "_omnix_live_chat_speculation_inline_stream_registered"


def register_live_chat_speculation_inline_stream_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
) -> None:
    """Register the one-request eager speculation stream."""

    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/live/speculation/sessions/{session_id}/start-stream",
        include_in_schema=False,
    )
    async def start_and_stream_live_speculation(
        session_id: str,
        request: speculation_runtime.LiveSpeculationRequest,
    ) -> StreamingResponse:
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
        generation = handshake_runtime._HandshakeGeneration(
            store=store,
            session=session,
        )
        worker = threading.Thread(
            target=handshake_runtime._run_generation,
            args=(pending, generation),
            name=f"omnix-live-speculation-{generation_id[-8:]}",
            daemon=True,
        )
        generation.worker = worker

        with speculation_runtime._SPECULATION_LOCK:
            speculation_runtime._prune_speculations()
            handshake_runtime._prune_handshake_state_locked()
            speculation_runtime._SPECULATIONS[generation_id] = pending
            handshake_runtime._HANDSHAKE_GENERATIONS[generation_id] = generation
            generation.stream_started = True
            handshake_runtime._STREAM_STARTED.add(generation_id)

        allocation_ms = (time.perf_counter() - started) * 1000.0
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_handshake_ready",
            generation_id=generation_id,
            cache_hit=cache_hit,
            session_load_ms=round(session_load_ms, 3),
            total_ms=round(allocation_ms, 3),
            generation_started=True,
            inline_stream=True,
            max_buffered_events=handshake_runtime._MAX_BUFFERED_EVENTS,
            max_buffered_bytes=handshake_runtime._MAX_BUFFERED_BYTES,
        )
        stream_log(
            "gateway-live-chat-speculation",
            "runtime",
            "live_chat_speculation_stream_attached",
            generation_id=generation_id,
            buffered_event_count=0,
            buffered_bytes=0,
            generation_completed=False,
            attach_delay_ms=round(allocation_ms, 3),
            inline_stream=True,
        )
        worker.start()

        def generate() -> Iterator[str]:
            yield speculation_runtime._speculation_started_sse(
                {
                    "type": "speculation_started",
                    "generation_id": generation_id,
                    "segment_id": request.segment_id,
                    "source_sequence": request.source_sequence,
                    "provider_id": pending.provider_id,
                    "model_id": pending.model_id,
                    "inline_stream": True,
                }
            )
            yield from handshake_runtime._subscribe_generation(
                generation_id,
                pending,
                generation,
            )

        headers = {
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
            "X-Omnix-Speculation-Generation-Id": generation_id,
            "X-Omnix-Speculation-Transport": "inline-v1",
        }
        if pending.provider_id:
            headers["X-Omnix-Speculation-Provider-Id"] = pending.provider_id
        if pending.model_id:
            headers["X-Omnix-Speculation-Model-Id"] = pending.model_id
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers=headers,
        )


__all__ = ["register_live_chat_speculation_inline_stream_routes"]
