"""Assistant-context chat works without the research feature (ADR-0016, PA-1.3)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.chat.assistant_context import routes as assistant_context_routes
from app.chat.assistant_context.models import AssistantContextBuildResult
from app.chat.assistant_context.routes import register_assistant_context_routes
from tests.support.in_memory_jobs import InMemoryJobStore

pytestmark = pytest.mark.usefixtures("legacy_test_persistence")


class _EmptyContextService:
    def __init__(self) -> None:
        self.requests = []

    def build(self, request):
        self.requests.append(request)
        return AssistantContextBuildResult()


def _app(tmp_path, monkeypatch):
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs")
    context_service = _EmptyContextService()
    session = chat_store.create_session(CreateChatSessionRequest(title="No research"))
    hooks = []

    def complete_accepted_job(**kwargs):
        job = kwargs["job"]
        message_id = job.input_payload["message_id"]
        context_items, diagnostics = kwargs["context_builder"]()
        kwargs["chat_store"].complete_streamed_reply(
            session.id, message_id, "Plain answer.", {"reply_to_message_id": message_id},
        )
        kwargs["completion_hook"](kwargs["chat_store"], session.id, message_id, context_items, diagnostics)
        hooks.append(diagnostics)
        return job

    monkeypatch.setattr(assistant_context_routes, "start_chat_generation_job", complete_accepted_job)
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=lambda: context_service,
        research_factory=lambda: None,
    )
    return TestClient(app), session, chat_store, hooks


def test_a_turn_without_research_runs_as_disabled(tmp_path, monkeypatch):
    client, session, chat_store, hooks = _app(tmp_path, monkeypatch)

    response = client.post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Hello", "web_research_mode": "disabled"},
    )

    assert response.status_code == 200
    assert hooks[0]["research_effective_mode"] == "disabled"
    assert hooks[0]["research_release_reason"] == "research_disabled_for_turn"
    reply = chat_store.get_session(session.id).messages[-1]
    assert reply.content == "Plain answer."
    assert reply.metadata["research_release_status"] == "allowed"


@pytest.mark.parametrize("mode", ["quick", "deep"])
def test_research_modes_are_unavailable_without_research(tmp_path, monkeypatch, mode):
    client, session, _chat_store, _hooks = _app(tmp_path, monkeypatch)

    response = client.post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Find it", "web_research_mode": mode},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "research_mode_unavailable",
        "requested_mode": mode,
        "reason": "research_feature_disabled",
        "available_modes": ["disabled"],
        "downgrade_available": False,
    }
