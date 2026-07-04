from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.chat.store import ChatSessionStore
from app.gateway.main import create_gateway_app, _live_job_event_stream, _parse_event_id, _sse_comment, _sse_event
from app.providers import ChatResponse


@dataclass
class FakeJobEvent:
    id: int
    event_type: str
    payload: dict[str, Any]

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        assert mode == "json"
        return {"id": self.id, "event_type": self.event_type, **self.payload}


class FakeJobStore:
    def __init__(self, events: list[FakeJobEvent]):
        self._events = events
        self.after_ids: list[int] = []

    def list_events(self, after_id: int, limit: int):
        self.after_ids.append(after_id)
        return [event for event in self._events if event.id > after_id][:limit]


class FakeTtsProvider:
    def __init__(self):
        self.batch_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def generate_audio(self, **kwargs: Any):
        self.batch_calls.append(kwargs)
        assert kwargs["text"] == "Hello from the podcast"
        assert kwargs["speaker"] == "Alex"
        assert kwargs["language"] == "English"
        assert kwargs["temperature"] == 0.6
        assert kwargs["top_k"] == 20
        assert kwargs["top_p"] == 0.85
        assert kwargs["repetition_penalty"] == 1.0
        assert kwargs["append_silence"] is False
        assert kwargs["max_new_tokens"] == 180
        assert kwargs["non_streaming_mode"] is False
        assert kwargs["parity_mode"] is True
        return {
            "success": True,
            "audio_base64": "AAD//w==",
            "sample_rate": 24000,
        }

    def generate_audio_stream(self, **kwargs: Any):
        self.stream_calls.append(kwargs)
        assert kwargs["text"] == "Hello from the podcast"
        assert kwargs["speaker"] == "Alex"
        assert kwargs["language"] == "English"
        assert kwargs["chunk_size"] == 8
        assert kwargs["temperature"] == 0.6
        assert kwargs["top_k"] == 20
        assert kwargs["top_p"] == 0.85
        assert kwargs["repetition_penalty"] == 1.0
        assert kwargs["append_silence"] is False
        assert kwargs["max_new_tokens"] == 180
        assert kwargs["non_streaming_mode"] is False
        assert kwargs["parity_mode"] is True
        yield [0.0, 0.25, -0.25], 24000, {"chunk_index": 0}


class BufferingFakeTtsProvider:
    def __init__(self):
        self.generated_chunks = 0

    def generate_audio_stream(self, **kwargs: Any):
        assert kwargs["non_streaming_mode"] is False
        for chunk_index in range(4):
            self.generated_chunks += 1
            yield [0.25, -0.25] * 1024, 24000, {"chunk_index": chunk_index}


class PartialFailureTtsProvider:
    def generate_audio_stream(self, **kwargs: Any):
        assert kwargs["non_streaming_mode"] is False
        yield [0.25, -0.25] * 2048, 24000, {"chunk_index": 0}
        raise RuntimeError("provider failed after first audio")


def test_sse_event_includes_optional_id_and_sorted_json_data():
    assert _sse_event("job.updated", {"z": 2, "a": 1}, event_id=42) == (
        'id: 42\n'
        'event: job.updated\n'
        'data: {"a": 1, "z": 2}\n\n'
    )


def test_sse_comment_and_event_id_parsing_are_tolerant():
    assert _sse_comment("heartbeat") == ": heartbeat\n\n"
    assert _parse_event_id("12") == 12
    assert _parse_event_id(None, fallback=7) == 7
    assert _parse_event_id("not-an-int", fallback=9) == 9


def test_live_job_event_stream_resumes_after_supplied_event_id():
    async def collect_first_three_chunks() -> tuple[list[str], list[int]]:
        store = FakeJobStore(
            [
                FakeJobEvent(id=1, event_type="job.created", payload={"job_id": "old"}),
                FakeJobEvent(id=2, event_type="job.updated", payload={"job_id": "current"}),
            ]
        )
        stream = _live_job_event_stream(store, after_id=1)
        try:
            chunks = [await anext(stream), await anext(stream), await anext(stream)]
        finally:
            await stream.aclose()
        return chunks, store.after_ids

    chunks, after_ids = asyncio.run(collect_first_three_chunks())

    assert chunks[0] == ": omnix-events-open\n\n"
    assert chunks[1] == (
        'id: 2\n'
        'event: job.updated\n'
        'data: {"event_type": "job.updated", "id": 2, "job_id": "current"}\n\n'
    )
    assert chunks[2] == ": heartbeat\n\n"
    assert after_ids[:2] == [1, 2]


def test_finite_job_events_endpoint_emits_sse_ids_and_honors_after_id():
    store = FakeJobStore(
        [
            FakeJobEvent(id=1, event_type="job.created", payload={"job_id": "old"}),
            FakeJobEvent(id=2, event_type="job.completed", payload={"job_id": "current"}),
        ]
    )
    app = create_gateway_app(job_store_factory=lambda: store)
    client = TestClient(app)

    response = client.get("/api/jobs/events?after_id=1&limit=5")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        'id: 2\n'
        'event: job.completed\n'
        'data: {"event_type": "job.completed", "id": 2, "job_id": "current"}\n\n'
    )
    assert store.after_ids == [1]


def test_tts_stream_releases_first_startup_chunk_promptly():
    from app.gateway import tts_streaming

    provider = BufferingFakeTtsProvider()
    request = tts_streaming.TtsStreamRequest(text="Buffered hello", non_streaming_mode=False)
    stream = tts_streaming._tts_sse_stream(provider, request, "Buffered hello")

    assert next(stream) == ": tts-stream-open\n\n"
    first_chunk = next(stream)

    assert provider.generated_chunks == 1
    assert '"chunk_index": 0' in first_chunk
    assert '"type": "chunk"' in first_chunk
    assert '"chunk_index": 1' in next(stream)
    assert provider.generated_chunks == 2


def test_tts_stream_reblocks_pcm16_without_altering_boundaries():
    from app.gateway import tts_streaming

    def pcm16(samples: list[int]) -> bytes:
        return b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)

    chunks = iter(
        [
            (pcm16([1000, 1000, 1000]), 1000, {"chunk_index": 0}),
            (pcm16([-1000, -1000, -1000]), 1000, {"chunk_index": 1}),
        ]
    )

    blocks = list(tts_streaming._stream_pcm16_blocks(chunks, block_samples=4, silence_threshold=0, preroll_ms=0))
    samples = [
        int.from_bytes(chunk[index : index + 2], "little", signed=True)
        for chunk, _sample_rate, _timing in blocks
        for index in range(0, len(chunk), 2)
    ]

    assert len(blocks) == 2
    assert samples == [1000, 1000, 1000, -1000, -1000, -1000, 0, 0]


def test_tts_stream_trims_initial_silence_with_preroll():
    from app.gateway import tts_streaming

    def pcm16(samples: list[int]) -> bytes:
        return b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)

    chunks = iter([(pcm16([0, 0, 0, 0, 1000, 1000, 1000, 1000]), 1000, {})])

    blocks = list(tts_streaming._stream_pcm16_blocks(chunks, block_samples=4, silence_threshold=0.01, preroll_ms=2))
    samples = [
        int.from_bytes(chunk[index : index + 2], "little", signed=True)
        for chunk, _sample_rate, _timing in blocks
        for index in range(0, len(chunk), 2)
    ]

    assert samples == [0, 0, 1000, 1000, 1000, 1000, 0, 0]


def test_tts_stream_finishes_partial_audio_when_provider_fails_after_first_chunk():
    from app.gateway import tts_streaming

    request = tts_streaming.TtsStreamRequest(text="Partial audio", non_streaming_mode=False)
    events = list(tts_streaming._tts_sse_stream(PartialFailureTtsProvider(), request, "Partial audio"))

    assert any('"type": "chunk"' in event for event in events)
    assert any('"type": "done"' in event and '"partial": true' in event for event in events)
    assert not any('"type": "error"' in event for event in events)


def test_tts_stream_endpoint_emits_voice_chunks(monkeypatch):
    from app.gateway import tts_streaming

    provider = FakeTtsProvider()
    monkeypatch.setattr(tts_streaming, "get_tts_provider", lambda: provider)
    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]))
    client = TestClient(app)

    response = client.post(
        "/api/tts/stream/server-sent-events",
        json={
            "text": "Hello from the podcast",
            "speaker": "Alex",
            "language": "English",
            "chunk_size": 8,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.0,
            "append_silence": False,
            "max_new_tokens": 180,
            "non_streaming_mode": True,
            "parity_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert ": tts-stream-open\n\n" in response.text
    assert '"type": "chunk"' in response.text
    assert '"sample_rate": 24000' in response.text
    assert '"type": "done"' in response.text
    assert provider.batch_calls == []
    assert len(provider.stream_calls) == 1


def test_tts_stream_endpoint_keeps_parity_mode_streaming_when_not_batch(monkeypatch):
    from app.gateway import tts_streaming

    provider = FakeTtsProvider()
    monkeypatch.setattr(tts_streaming, "get_tts_provider", lambda: provider)
    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]))
    client = TestClient(app)

    response = client.post(
        "/api/tts/stream/server-sent-events",
        json={
            "text": "Hello from the podcast",
            "speaker": "Alex",
            "language": "English",
            "chunk_size": 8,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.0,
            "append_silence": False,
            "max_new_tokens": 180,
            "non_streaming_mode": False,
            "parity_mode": True,
        },
    )

    assert response.status_code == 200
    assert '"type": "chunk"' in response.text
    assert '"type": "done"' in response.text
    assert provider.batch_calls == []
    assert len(provider.stream_calls) == 1


def test_chat_session_delete_endpoint_removes_session(tmp_path):
    store = ChatSessionStore(tmp_path / "chat.json")
    first = store.create_session(type("Request", (), {"title": "First", "provider_id": "fake", "model_id": "fake-model", "system_prompt": None})())
    second = store.create_session(type("Request", (), {"title": "Second", "provider_id": "fake", "model_id": "fake-model", "system_prompt": None})())
    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]), chat_store_factory=lambda: store)
    client = TestClient(app)

    response = client.delete(f"/api/chat/sessions/{first.id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "session_id": first.id}
    assert store.get_session(first.id) is None
    assert store.get_session(second.id) is not None
    listing = client.get("/api/chat/sessions")
    assert first.id not in listing.text
    assert second.id in listing.text
    assert client.delete(f"/api/chat/sessions/{first.id}").status_code == 404


def test_chat_stream_endpoint_emits_sentence_chunks_and_persists_session(monkeypatch, tmp_path):
    from app import shared

    class FakeChatProvider:
        def chat_completion(self, **_: Any):
            yield ChatResponse(content="Hello there. ", model="fake-model")
            yield ChatResponse(content="I can hear you now.", model="fake-model")

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(type("Request", (), {"title": "Voice", "provider_id": "fake", "model_id": "fake-model", "system_prompt": None})())
    monkeypatch.setattr(shared, "get_provider", lambda _provider_name=None: FakeChatProvider())

    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]), chat_store_factory=lambda: store)
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={"content": "Can you hear me?", "provider_id": "fake", "model_id": "fake-model"},
    )

    assert response.status_code == 200
    assert '"type": "user_message"' in response.text
    assert '"text": "Hello there."' in response.text
    assert '"text": "I can hear you now."' in response.text
    assert '"type": "session"' in response.text
    saved = store.get_session(session.id)
    assert saved is not None
    assert saved.messages[-1].role == "assistant"
    assert saved.messages[-1].content == "Hello there. I can hear you now."
