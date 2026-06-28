from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app, _live_job_event_stream, _parse_event_id, _sse_comment, _sse_event


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
    def generate_audio_stream(self, **kwargs: Any):
        assert kwargs["text"] == "Hello from the podcast"
        assert kwargs["speaker"] == "Alex"
        assert kwargs["language"] == "en"
        yield [0.0, 0.25, -0.25], 24000, {"chunk_index": 0}


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


def test_tts_stream_endpoint_emits_voice_chunks(monkeypatch):
    from app.gateway import tts_streaming

    monkeypatch.setattr(tts_streaming, "get_tts_provider", lambda: FakeTtsProvider())
    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]))
    client = TestClient(app)

    response = client.post(
        "/api/tts/stream/server-sent-events",
        json={"text": "Hello from the podcast", "speaker": "Alex", "language": "en"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert ": tts-stream-open\n\n" in response.text
    assert '"type": "chunk"' in response.text
    assert '"sample_rate": 24000' in response.text
    assert '"type": "done"' in response.text
