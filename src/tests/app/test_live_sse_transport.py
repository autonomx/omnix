from __future__ import annotations

from tests.support.routers import effective_routes

import asyncio
import threading

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from app.chat.assistant_turns import AssistantTurnCoordinator
from app.chat.models import SendChatMessageRequest
from app.live_voice.transport.sse import OmnixStreamingResponse

_LIVE_CHAT_STREAM_PATH = "/api/chat/sessions/{session_id}/messages/stream"


def _collect(response: StreamingResponse) -> list[bytes]:
    async def collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(
                chunk if isinstance(chunk, bytes) else chunk.encode(response.charset)
            )
        return chunks

    return asyncio.run(collect())


def test_live_sse_response_adds_preamble_and_anti_buffering_headers(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "2048")
    starlette_init = StreamingResponse.__init__

    response = OmnixStreamingResponse(
        iter(["data: first\n\n"]),
        media_type="text/event-stream",
    )
    chunks = _collect(response)

    assert StreamingResponse.__init__ is starlette_init
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


def test_synchronous_sse_remains_consumer_driven_without_eager_option(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "8")
    source_started = threading.Event()

    def source():
        source_started.set()
        yield "data: first\n\n"
        yield "data: second\n\n"

    async def scenario() -> tuple[list[bytes], str]:
        response = OmnixStreamingResponse(
            source(),
            media_type="text/event-stream",
        )
        await asyncio.sleep(0.05)
        assert not source_started.is_set()
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(
                chunk if isinstance(chunk, bytes) else chunk.encode(response.charset)
            )
        return chunks, response.headers["x-omnix-sse-execution"]

    chunks, execution_mode = asyncio.run(scenario())

    assert len(chunks[0]) == 8
    assert chunks[1:] == [b"data: first\n\n", b"data: second\n\n"]
    assert execution_mode == "starlette-sync"


def test_live_chat_route_explicitly_eagerly_executes_sync_provider(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "8")
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
    ) -> OmnixStreamingResponse:
        return OmnixStreamingResponse(
            source(),
            media_type="text/event-stream",
            eager_sync=True,
            diagnostic_context={
                "route_path": _LIVE_CHAT_STREAM_PATH,
                "session_id": session_id,
                "user_turn_id": request.user_turn_id,
                "speech_segment_id": request.speech_segment_id,
            },
        )

    route = next(
        route.original_route
        for route in effective_routes(gateway)
        if isinstance(route.original_route, APIRoute) and route.path == _LIVE_CHAT_STREAM_PATH
    )

    async def scenario() -> tuple[StreamingResponse, list[bytes]]:
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
            chunks.append(
                chunk if isinstance(chunk, bytes) else chunk.encode(response.charset)
            )
        return response, chunks

    response, chunks = asyncio.run(scenario())

    assert response.headers["x-omnix-sse-transport"] == "immediate-v4"
    assert response.headers["x-omnix-sse-execution"] == "eager-route"
    assert len(chunks[0]) == 8
    assert chunks[1:] == [b"data: user-message\n\n", b"data: provider-first-text\n\n"]


def test_assistant_turn_can_start_running_in_one_native_durable_write(tmp_path) -> None:
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    original_save = coordinator._save
    save_count = 0

    def counted_save() -> None:
        nonlocal save_count
        save_count += 1
        original_save()

    coordinator._save = counted_save  # type: ignore[method-assign]

    turn = coordinator.start_streaming(
        session_id="chat:running",
        user_message_id="msg:user",
        user_turn_id="voice-user-turn:running",
        speech_segment_id="voice-segment:running",
    )
    repeated = coordinator.start_streaming(
        session_id="chat:running",
        user_message_id="msg:user",
        user_turn_id="voice-user-turn:running",
        speech_segment_id="voice-segment:running",
    )

    assert turn.lifecycle == "streaming"
    assert turn.provider_execution == "running"
    assert repeated.assistant_turn_id == turn.assistant_turn_id
    assert save_count == 1
    reloaded = AssistantTurnCoordinator(tmp_path / "assistant-turns.json").get(
        turn.assistant_turn_id
    )
    assert reloaded is not None
    assert reloaded.lifecycle == "streaming"
    assert reloaded.provider_execution == "running"


def test_nonstream_response_contract_is_unchanged() -> None:
    response = StreamingResponse(iter(["plain text"]), media_type="text/plain")
    assert _collect(response) == [b"plain text"]
    assert "x-accel-buffering" not in response.headers
    assert "x-omnix-sse-transport" not in response.headers


def test_live_sse_preamble_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "0")
    response = OmnixStreamingResponse(
        iter(["data: first\n\n"]),
        media_type="text/event-stream",
    )

    assert _collect(response) == [b"data: first\n\n"]
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-omnix-sse-transport"] == "immediate-v4"
