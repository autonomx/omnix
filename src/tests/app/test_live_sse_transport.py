from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from app.chat.assistant_turns import AssistantTurnCoordinator
from app.chat.models import SendChatMessageRequest
from app.gateway.live_sse_transport import (
    install_live_chat_sse_route_execution,
    install_live_sse_transport_hook,
)

_LIVE_CHAT_STREAM_PATH = "/api/chat/sessions/{session_id}/messages/stream"


def _collect(response: StreamingResponse) -> list[bytes]:
    async def collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode(response.charset))
        return chunks

    return asyncio.run(collect())


def test_event_stream_has_flush_preamble_and_anti_buffering_headers(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "2048")
    install_live_sse_transport_hook()

    response = StreamingResponse(
        iter(["data: first\n\n"]),
        media_type="text/event-stream",
    )
    chunks = _collect(response)

    assert len(chunks[0]) == 2048
    assert chunks[0].startswith(b":")
    assert chunks[0].endswith(b"\n\n")
    assert chunks[1] == b"data: first\n\n"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-omnix-sse-transport"] == "immediate-v4"
    assert response.headers["x-omnix-sse-execution"] == "starlette-sync"
    assert "no-cache" in response.headers["cache-control"]
    assert "no-transform" in response.headers["cache-control"]


def test_generic_sync_event_stream_remains_consumer_driven(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "8")
    install_live_sse_transport_hook()
    source_started = threading.Event()

    def source():
        source_started.set()
        yield "data: first\n\n"
        yield "data: second\n\n"

    async def scenario() -> list[bytes]:
        response = StreamingResponse(source(), media_type="text/event-stream")
        await asyncio.sleep(0.05)
        assert not source_started.is_set()
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode(response.charset))
        assert response.headers["x-omnix-sse-execution"] == "starlette-sync"
        return chunks

    chunks = asyncio.run(scenario())

    assert len(chunks[0]) == 8
    assert chunks[1:] == [b"data: first\n\n", b"data: second\n\n"]


def test_accepted_chat_stream_runs_provider_before_consumer_read(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "8")
    install_live_sse_transport_hook()
    provider_entered = threading.Event()

    def source():
        yield b"data: user-message\n\n"
        provider_entered.set()
        yield "data: provider-first-text\n\n"

    gateway = FastAPI(title="Omnix Web Gateway")

    @gateway.post(_LIVE_CHAT_STREAM_PATH)
    async def stream_chat_message(
        session_id: str,
        request: SendChatMessageRequest,
    ) -> StreamingResponse:
        del session_id, request
        return StreamingResponse(source(), media_type="text/event-stream")

    route = next(
        route
        for route in gateway.routes
        if isinstance(route, APIRoute) and route.path == _LIVE_CHAT_STREAM_PATH
    )

    async def scenario() -> tuple[StreamingResponse, list[bytes]]:
        async with gateway.router.lifespan_context(gateway):
            assert install_live_chat_sse_route_execution(gateway) == []
            response = await route.dependant.call(
                session_id="chat:test",
                request=SendChatMessageRequest(
                    content="hello",
                    user_turn_id="voice-user-turn:voice-turn:test",
                    speech_segment_id="voice-segment:test",
                ),
            )
            await asyncio.sleep(0.05)
            assert provider_entered.is_set()
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode(response.charset))
            return response, chunks

    response, chunks = asyncio.run(scenario())

    assert response.headers["x-omnix-sse-transport"] == "immediate-v4"
    assert response.headers["x-omnix-sse-execution"] == "eager-route"
    assert len(chunks[0]) == 8
    assert chunks[1:] == [
        b"data: user-message\n\n",
        b"data: provider-first-text\n\n",
    ]


def test_accepted_chat_turn_starts_running_in_one_durable_write(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "8")
    install_live_sse_transport_hook()
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    original_save = coordinator._save
    save_count = 0
    provider_entered = threading.Event()
    assistant_turn_id = ""

    def counted_save() -> None:
        nonlocal save_count
        save_count += 1
        original_save()

    coordinator._save = counted_save  # type: ignore[method-assign]

    def source():
        yield "data: user-message\n\n"
        coordinator.mark_streaming(assistant_turn_id)
        provider_entered.set()
        yield "data: provider-first-text\n\n"

    gateway = FastAPI(title="Omnix Web Gateway")

    @gateway.post(_LIVE_CHAT_STREAM_PATH)
    async def stream_chat_message(
        session_id: str,
        request: SendChatMessageRequest,
    ) -> StreamingResponse:
        nonlocal assistant_turn_id
        turn = coordinator.start(
            session_id=session_id,
            user_message_id="msg:user",
            user_turn_id=request.user_turn_id or "voice-user-turn:test",
            speech_segment_id=request.speech_segment_id,
        )
        assistant_turn_id = turn.assistant_turn_id
        assert turn.lifecycle == "streaming"
        assert turn.provider_execution == "running"
        return StreamingResponse(source(), media_type="text/event-stream")

    route = next(
        route
        for route in gateway.routes
        if isinstance(route, APIRoute) and route.path == _LIVE_CHAT_STREAM_PATH
    )

    async def scenario() -> list[bytes]:
        async with gateway.router.lifespan_context(gateway):
            response = await route.dependant.call(
                session_id="chat:running",
                request=SendChatMessageRequest(
                    content="hello",
                    user_turn_id="voice-user-turn:running",
                    speech_segment_id="voice-segment:running",
                ),
            )
            await asyncio.sleep(0.05)
            assert provider_entered.is_set()
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode(response.charset))
            return chunks

    chunks = asyncio.run(scenario())

    assert save_count == 1
    assert chunks[1:] == [
        b"data: user-message\n\n",
        b"data: provider-first-text\n\n",
    ]
    reloaded = AssistantTurnCoordinator(tmp_path / "assistant-turns.json").get(
        assistant_turn_id
    )
    assert reloaded is not None
    assert reloaded.lifecycle == "streaming"
    assert reloaded.provider_execution == "running"


def test_nonstream_assistant_turn_start_contract_is_unchanged(tmp_path) -> None:
    install_live_sse_transport_hook()
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")

    turn = coordinator.start(
        session_id="chat:queued",
        user_message_id="msg:user",
        user_turn_id="user-turn:queued",
    )

    assert turn.lifecycle == "created"
    assert turn.provider_execution == "not_started"
    running = coordinator.mark_streaming(turn.assistant_turn_id)
    assert running is not None
    assert running.lifecycle == "streaming"
    assert running.provider_execution == "running"


def test_non_event_stream_is_not_modified(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "2048")
    install_live_sse_transport_hook()

    response = StreamingResponse(iter(["plain text"]), media_type="text/plain")
    chunks = _collect(response)

    assert chunks == [b"plain text"]
    assert "x-accel-buffering" not in response.headers
    assert "x-omnix-sse-transport" not in response.headers
    assert "x-omnix-sse-execution" not in response.headers


def test_event_stream_preamble_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "0")
    install_live_sse_transport_hook()

    response = StreamingResponse(iter(["data: first\n\n"]), media_type="text/event-stream")
    chunks = _collect(response)

    assert chunks == [b"data: first\n\n"]
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-omnix-sse-transport"] == "immediate-v4"
    assert response.headers["x-omnix-sse-execution"] == "starlette-sync"
