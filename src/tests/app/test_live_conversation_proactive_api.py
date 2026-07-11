from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.characters import api as character_api
from app.gateway.main import create_gateway_app


def _create_session(client: TestClient) -> str:
    response = client.post("/api/chat/sessions", json={"title": "Proactive live chat"})
    assert response.status_code == 200
    return response.json()["id"]


def test_proactive_stream_is_transient_until_delivery_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_LIVE_CONVERSATION_PROFILE_PATH", str(tmp_path / "profiles.json"))
    client = TestClient(create_gateway_app())
    session_id = _create_session(client)

    def fake_proactive_stream(_store, session, **kwargs):
        assert session.id == session_id
        assert kwargs["initiative_reason"] == "unresolved_question"
        yield {
            "type": "initiative",
            "turn_id": "proactive:one",
            "initiative_reason": "unresolved_question",
        }
        yield {"type": "text_chunk", "text": "Want to keep working through that?"}
        yield {
            "type": "complete",
            "content": "Want to keep working through that?",
            "metadata": {
                "purpose": "proactive_reengagement",
                "transient": True,
                "turn_id": "proactive:one",
                "initiative_reason": "unresolved_question",
            },
        }

    monkeypatch.setattr(character_api, "stream_proactive_turn_chunks", fake_proactive_stream)
    before = client.get(f"/api/chat/sessions/{session_id}").json()

    response = client.post(
        f"/api/chat/sessions/{session_id}/live-call/greeting/stream",
        params={
            "purpose": "proactive_reengagement",
            "initiative_reason": "unresolved_question",
            "state_summary": "stance=discuss",
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["turn_id"] == "proactive:one"
    assert events[1]["type"] == "text_chunk"
    assert events[-1] == {"type": "done"}
    after_generation = client.get(f"/api/chat/sessions/{session_id}").json()
    assert after_generation["message_count"] == before["message_count"]

    delivery = {
        "turn_id": "proactive:one",
        "content": "Want to keep working through that?",
        "initiative_reason": "unresolved_question",
        "delivery_status": "completed",
    }
    committed = client.post(
        f"/api/chat/sessions/{session_id}/live-conversation/proactive/delivery",
        json=delivery,
    )
    assert committed.status_code == 200
    assert committed.json()["duplicate"] is False
    session = committed.json()["session"]
    assert session["message_count"] == before["message_count"] + 1
    message = session["messages"][-1]
    assert message["role"] == "assistant"
    assert message["metadata"]["purpose"] == "proactive_reengagement"
    assert message["metadata"]["delivery_status"] == "completed"

    duplicate = client.post(
        f"/api/chat/sessions/{session_id}/live-conversation/proactive/delivery",
        json=delivery,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["session"]["message_count"] == session["message_count"]


def test_proactive_delivery_requires_existing_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/chat/sessions/chat:missing/live-conversation/proactive/delivery",
        json={
            "turn_id": "proactive:missing",
            "content": "Still there?",
            "initiative_reason": "continue_current_topic",
            "delivery_status": "completed",
        },
    )

    assert response.status_code == 404
