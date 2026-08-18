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
    assert response.text.endswith(
        'id: 2\n'
        'event: job.completed\n'
        'data: {"event_type": "job.completed", "id": 2, "job_id": "current"}\n\n'
    )
    assert response.text[:1] in {":", "i"}
    assert store.after_ids == [1]


def test_legacy_tts_sse_endpoint_is_removed():
    app = create_gateway_app(job_store_factory=lambda: FakeJobStore([]))
    client = TestClient(app)

    response = client.post(
        "/api/tts/stream/server-sent-events",
        json={"text": "This transport has been retired."},
    )

    assert response.status_code == 404


def test_chat_session_delete_endpoint_removes_session(tmp_path):
    store = ChatSessionStore(tmp_path / "chat.json")
    first = store.create_session(
        type(
            "Request",
            (),
            {
                "title": "First",
                "provider_id": "fake",
                "model_id": "fake-model",
                "system_prompt": None,
            },
        )()
    )
    second = store.create_session(
        type(
            "Request",
            (),
            {
                "title": "Second",
                "provider_id": "fake",
                "model_id": "fake-model",
                "system_prompt": None,
            },
        )()
    )
    app = create_gateway_app(
        job_store_factory=lambda: FakeJobStore([]),
        chat_store_factory=lambda: store,
    )
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

    class CompletionOrderingStore(ChatSessionStore):
        completion_persisted = False

        def stream_provider_reply_chunks(self, *args, **kwargs):
            yield from super().stream_provider_reply_chunks(*args, **kwargs)
            assert self.completion_persisted, (
                "assistant completion must be durable before the provider stream resumes"
            )

        def complete_streamed_reply(self, *args, **kwargs):
            completed = super().complete_streamed_reply(*args, **kwargs)
            self.completion_persisted = True
            return completed

    class FakeChatProvider:
        def chat_completion(self, **_: Any):
            yield ChatResponse(content="Hello there. ", model="fake-model")
            yield ChatResponse(content="I can hear you now.", model="fake-model")

    store = CompletionOrderingStore(tmp_path / "chat.json")
    session = store.create_session(
        type(
            "Request",
            (),
            {
                "title": "Voice",
                "provider_id": "fake",
                "model_id": "fake-model",
                "system_prompt": None,
            },
        )()
    )
    monkeypatch.setattr(shared, "get_provider", lambda _provider_name=None: FakeChatProvider())

    app = create_gateway_app(
        job_store_factory=lambda: FakeJobStore([]),
        chat_store_factory=lambda: store,
    )
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={
            "content": "Can you hear me?",
            "provider_id": "fake",
            "model_id": "fake-model",
        },
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
