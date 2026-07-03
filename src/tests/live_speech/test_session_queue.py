from __future__ import annotations

import pytest

from app.live_speech.session_queue import QueuedLiveSpeechSession


@pytest.mark.asyncio
async def test_queued_session_starts_with_session_created() -> None:
    session = QueuedLiveSpeechSession()

    await session.start()
    events = await session.drain_available()

    assert [evt.type for evt in events] == ["session.created"]


@pytest.mark.asyncio
async def test_queued_session_handles_text_response_flow() -> None:
    session = QueuedLiveSpeechSession()

    await session.handle({"type": "conversation.item.create", "item": {"type": "input_text", "text": "hello"}})
    await session.handle({"type": "response.create"})
    events = await session.drain_available()
    event_types = [evt.type for evt in events]

    assert "conversation.item.created" in event_types
    assert "response.created" in event_types
    assert "response.output_audio.delta" in event_types
    assert "response.done" in event_types


@pytest.mark.asyncio
async def test_queued_session_ignores_messages_after_close() -> None:
    session = QueuedLiveSpeechSession()
    await session.close()

    await session.handle({"type": "response.create"})
    events = await session.drain_available()

    assert events == []
