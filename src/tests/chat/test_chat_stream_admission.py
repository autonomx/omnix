"""The Chat streaming route shares the job route's admission (WP-8.5)."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.platform.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.platform.chat.admission import admit_chat_turn, stream_chat_turn
from app.platform.chat.generation_jobs import interrupt_active_chat_generation_jobs
from app.composition.gateway.main import create_gateway_app
from app.jobs.models import JobStatus
from tests.support.in_memory_jobs import InMemoryJobStore

# Composes the PostgreSQL-backed gateway; runs in the test-postgres job.
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

    def __init__(self, path, reply: str = "Hello there.") -> None:
        super().__init__(path)
        self.reply = reply
        self.streams = 0

    def stream_provider_reply_chunks(self, session, user_message, **_kwargs):
        self.streams += 1
        yield {"type": "delta", "content": "Hello"}
        yield {"type": "delta", "content": " there."}
        yield {"type": "complete", "content": self.reply, "metadata": {"generation_status": "completed"}}


def _session(store: ChatSessionStore):
    return store.create_session(CreateChatSessionRequest(
        title="Streamed", provider_id="llm:lmstudio", model_id="llm:lmstudio:test-model",
    ))


def _stream(client: TestClient, session_id: str, turn_id: str) -> list[dict]:
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"content": "hello", "user_turn_id": turn_id},
    )
    assert response.status_code == 200
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines()
            if line.startswith("data: ")]


def _client(chat_store, job_store) -> TestClient:
    app = create_gateway_app(chat_store_factory=lambda: chat_store, job_store_factory=lambda: job_store)
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})


def test_a_streamed_turn_is_a_job_that_completes_with_its_reply(tmp_path):
    chat_store = ScriptedStreamStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)

    events = _stream(_client(chat_store, job_store), session.id, "turn-1")

    assert [event["type"] for event in events] == [
        "user_message", "job", "delta", "delta", "complete", "session", "done",
    ]
    job = job_store.get_job(events[1]["job"]["id"])
    assert job.status == JobStatus.COMPLETED
    assert job.output_refs[0]["type"] == "chat_response"
    assert chat_store.get_session(session.id).messages[-1].content == "Hello there."


def test_a_repeated_stream_submission_returns_the_existing_job(tmp_path):
    chat_store = ScriptedStreamStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)
    client = _client(chat_store, job_store)

    first = _stream(client, session.id, "turn-1")
    again = _stream(client, session.id, "turn-1")

    assert again[1]["job"]["id"] == first[1]["job"]["id"]
    assert [event["type"] for event in again] == ["user_message", "job", "session", "done"]
    assert chat_store.streams == 1  # nothing generated twice
    user_turns = [message for message in chat_store.get_session(session.id).messages if message.role == "user"]
    assert len(user_turns) == 1


def test_a_newer_submission_interrupts_a_streaming_turn(tmp_path):
    chat_store = ScriptedStreamStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)
    request = SendChatMessageRequest(content="first", user_turn_id="turn-1")
    admission = admit_chat_turn(chat_store, job_store, session.id, request)

    events = stream_chat_turn(chat_store, job_store, admission, request)
    assert next(events)["type"] == "delta"
    interrupt_active_chat_generation_jobs(
        chat_store, job_store, session_id=session.id, reason="Interrupted by a newer Chat prompt.",
    )

    assert next(events) == {"type": "interrupted", "job_id": admission.job.id}
    assert list(events) == []
    assert job_store.get_job(admission.job.id).status == JobStatus.CANCELED
