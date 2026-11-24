"""Assistant-context Chat turns go through the shared Chat admission (WP-8.5)."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.platform.chat.assistant_context.routes import register_assistant_context_routes
from app.platform.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.platform.chat.admission import admit_chat_turn
from app.conversation.contracts import AssistantContextItem
from app.jobs.models import JobStatus
from tests.support.in_memory_jobs import InMemoryJobStore

# The Chat store keeps its transcript through the PostgreSQL identity.
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def local_identity():
    if os.environ.get("OMNIX_TEST_DATABASE_URL") or os.environ.get("OMNIX_DATABASE_URL"):
        from app.persistence.database import default_database
        from app.persistence.identity_service import ensure_local_identity

        ensure_local_identity(default_database())
    yield


class ScriptedStreamStore(ChatSessionStore):
    """A Chat store whose provider stream is a fixed script of events."""

    def __init__(self, path) -> None:
        super().__init__(path)
        self.context_items_seen: list[object] = []

    def stream_provider_reply_chunks(self, session, user_message, **kwargs):
        self.context_items_seen.append(kwargs.get("context_items"))
        yield {"type": "delta", "content": "It is sunny."}
        yield {"type": "complete", "content": "It is sunny.", "metadata": {"generation_status": "completed"}}


class CountingContextService:
    def __init__(self) -> None:
        self.builds = 0

    def build(self, _request):
        self.builds += 1
        item = AssistantContextItem(source_id="web_search", title="Weather", content="Sunny today.")
        return SimpleNamespace(items=[item], diagnostics={"source_count": 1})


def _client(chat_store, job_store, context_service) -> TestClient:
    router = APIRouter()
    register_assistant_context_routes(
        router,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=lambda: context_service,
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, base_url="http://127.0.0.1")


def _stream(client: TestClient, session_id: str, turn_id: str) -> list[dict]:
    response = client.post(
        f"/api/assistant/context/chat/sessions/{session_id}/messages/stream",
        json={"content": "What is the weather?", "user_turn_id": turn_id, "web_research_mode": "disabled"},
    )
    assert response.status_code == 200
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines()
            if line.startswith("data: ")]


def _setup(tmp_path):
    chat_store = ScriptedStreamStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    context = CountingContextService()
    session = chat_store.create_session(CreateChatSessionRequest(
        title="Assistant", provider_id="llm:lmstudio", model_id="llm:lmstudio:test-model",
    ))
    return chat_store, job_store, context, session


def test_a_streamed_assistant_turn_is_a_job_that_completes_with_its_context(tmp_path):
    chat_store, job_store, context, session = _setup(tmp_path)

    events = _stream(_client(chat_store, job_store, context), session.id, "turn-1")

    assert [event["type"] for event in events] == [
        "user_message", "job", "delta", "complete", "session", "done",
    ]
    job = job_store.get_job(events[1]["job"]["id"])
    assert job.status == JobStatus.COMPLETED
    assert job.compat["contract"] == "assistant_context_chat_v1"
    assert "research_release" in job.input_payload
    assert chat_store.context_items_seen[0][0]["source_id"] == "web_search"
    reply = chat_store.get_session(session.id).messages[-1]
    assert reply.content == "It is sunny."
    assert reply.metadata["context_sources"] == ["web_search"]
    assert reply.metadata["context_diagnostics"]["source_count"] == 1


def test_a_repeated_assistant_stream_returns_the_existing_job_without_researching_again(tmp_path):
    chat_store, job_store, context, session = _setup(tmp_path)
    client = _client(chat_store, job_store, context)

    first = _stream(client, session.id, "turn-1")
    again = _stream(client, session.id, "turn-1")

    assert again[1]["job"]["id"] == first[1]["job"]["id"]
    assert [event["type"] for event in again] == ["user_message", "job", "session", "done"]
    assert context.builds == 1
    assert len(chat_store.context_items_seen) == 1
    user_turns = [message for message in chat_store.get_session(session.id).messages if message.role == "user"]
    assert len(user_turns) == 1


def test_a_shared_camera_is_looked_at_inside_the_stream_after_the_turn_is_shown(tmp_path, monkeypatch):
    # Review 2026-11-22: the look (up to 8 s for a typed turn) ran before the stream began, so the person's message
    # appeared only once the picture was described.
    from app.platform.chat.assistant_context import routes

    import asyncio

    from app.platform.chat.assistant_context.models import AssistantContextChatRequest

    chat_store, job_store, context, session = _setup(tmp_path)
    events: list[dict] = []
    looks: list[list[str]] = []  # the events the person had been sent when the camera was looked at

    def shared_picture_context(store, session_id, user_message, *, camera, screen):
        assert (camera, screen) == (True, False)
        looks.append([event["type"] for event in events])
        return [{"source_id": "camera", "title": "Camera", "content": "A mug on a desk."}]

    monkeypatch.setattr(routes, "shared_picture_context", shared_picture_context)
    client = _client(chat_store, job_store, context)
    router = APIRouter()  # the test client buffers a stream, so its body is stepped here
    register_assistant_context_routes(router, chat_store_factory=lambda: chat_store,
                                      job_store_factory=lambda: job_store, context_service_factory=lambda: context)
    endpoint = next(route.endpoint for route in router.routes
                    if getattr(route, "name", "") == "assistant_context_stream_chat_message_endpoint")
    body = {"content": "What is this?", "user_turn_id": "turn-1", "web_research_mode": "disabled",
            "camera_shared": True}

    async def stream() -> None:
        response = await endpoint(session.id, AssistantContextChatRequest(**body))
        async for chunk in response.body_iterator:
            events.append(json.loads(chunk.removeprefix("data: ")))

    asyncio.run(stream())

    assert [event["type"] for event in events] == ["user_message", "job", "delta", "complete", "session", "done"]
    assert looks == [["user_message", "job"]]
    assert [item["source_id"] for item in chat_store.context_items_seen[0]] == ["web_search", "camera"]
    client.post(f"/api/assistant/context/chat/sessions/{session.id}/messages/stream", json=body)
    assert len(looks) == 1  # a repeated submission reports its turn without a second look


def test_an_assistant_stream_interrupts_an_older_active_turn(tmp_path):
    chat_store, job_store, context, session = _setup(tmp_path)
    older = admit_chat_turn(
        chat_store, job_store, session.id, SendChatMessageRequest(content="first", user_turn_id="turn-0"),
    )
    assert job_store.get_job(older.job.id).status == JobStatus.QUEUED

    events = _stream(_client(chat_store, job_store, context), session.id, "turn-1")

    assert events[-1]["type"] == "done"
    assert job_store.get_job(older.job.id).status == JobStatus.CANCELED
