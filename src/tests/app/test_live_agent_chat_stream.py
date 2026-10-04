from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.chat.assist.modes import ModeChatResponse
from app.characters.repository import InMemoryCharacterRepository
from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.gateway.main import create_gateway_app
from tests.support.in_memory_jobs import InMemoryJobStore


class StaticPlanner:
    def __init__(self, response: ModeChatResponse) -> None:
        self.response = response

    def plan_proposal(self, **kwargs):
        return self.response


def _events(body: str) -> list[dict]:
    rows = []
    for block in body.split("\n\n"):
        data = "\n".join(
            line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
        )
        if data:
            rows.append(json.loads(data))
    return rows


def test_live_voice_action_streams_a_hermes_review_proposal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    monkeypatch.setenv("OMNIX_ASSISTANT_TURN_STORE_PATH", str(tmp_path / "turns.json"))
    from app.chat.assistant_turns import AssistantTurnCoordinator

    coordinator = AssistantTurnCoordinator(tmp_path / "turns.json")
    monkeypatch.setattr(
        "app.chat.live_agent_store.default_assistant_turn_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(
        "app.chat.character_store.default_assistant_turn_coordinator",
        lambda *_args, **_kwargs: coordinator,
    )
    planner = StaticPlanner(
        ModeChatResponse(
            ok=True,
            mode="agent",
            backend="hermes",
            result={
                "success": True,
                "response": "Proposal ready. Review it before the message is sent.",
                "domain": "chat",
                "tool_calls": [{"name": "send_message", "args": {"recipient": "Alex"}}],
                "tool_results": [],
                "requires_confirmation": True,
                "error": None,
            },
        )
    )
    store = ChatSessionStore(
        tmp_path / "chat.json",
        live_agent_planner=planner,
    )
    characters = InMemoryCharacterRepository(tmp_path / "characters.sqlite3")
    monkeypatch.setattr(
        "app.chat.character_store._character_repository",
        lambda: characters,
    )
    session = store.create_session(CreateChatSessionRequest(title="Live Agent"))
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    app = create_gateway_app(
        job_store_factory=lambda: job_store,
        chat_store_factory=lambda: store,
    )
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test"},
    )

    response = client.post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={
            "content": "Send a message to Alex",
            "user_turn_id": "voice-user-turn:test",
            "speech_segment_id": "voice-segment:test",
        },
    )

    assert response.status_code == 200
    events = _events(response.text)
    completion = next(row for row in events if row["type"] == "complete")
    persisted = next(row["session"] for row in events if row["type"] == "session")
    assert completion["metadata"]["backend"] == "hermes"
    assert completion["metadata"]["proposal_only"] is True
    assert completion["metadata"]["review_required"] is True
    assert completion["metadata"]["executes"] is False
    assistant = persisted["messages"][-1]
    assert assistant["metadata"]["live_agent"] is True
    assert assistant["metadata"]["live_agent_route"]["route"] == "agent_plan"
    assert events[-1]["type"] == "done"
