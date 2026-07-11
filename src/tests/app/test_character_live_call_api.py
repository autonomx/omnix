from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.characters import api as character_api
from app.gateway.main import create_gateway_app


def _create_character_session(client: TestClient) -> str:
    created_character = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_greeting": "Hey, good to hear from you.",
            "speech_style": {
                "speed": 0.94,
                "expressiveness": "relaxed",
                "default_emotion": "calm",
            },
        },
    )
    assert created_character.status_code == 201

    created_session = client.post(
        "/api/chat/sessions",
        json={
            "title": "Maya live call",
            "interaction_mode": "character",
            "character_id": "maya",
        },
    )
    assert created_session.status_code == 200
    return created_session.json()["id"]


def test_live_call_runtime_api_resolves_character_without_browser_prompt_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    session_id = _create_character_session(client)

    response = client.get(
        f"/api/chat/sessions/{session_id}/live-call/runtime"
    )

    assert response.status_code == 200
    runtime = response.json()
    assert runtime["interaction_mode"] == "character"
    assert runtime["character_id"] == "maya"
    assert runtime["display_name"] == "Maya"
    assert runtime["greeting"] == ""
    assert runtime["speech_style"]["speed"] == 0.94
    assert runtime["speech_style"]["emotion"] == "calm"
    assert runtime["character_profile_version"] == 1
    assert len(runtime["effective_identity_hash"]) == 64
    assert runtime["preload"]["profile_loaded"] is True


def test_live_call_greeting_stream_is_generated_and_transient(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    session_id = _create_character_session(client)
    before = client.get(f"/api/chat/sessions/{session_id}").json()

    def fake_greeting_stream(_store, session):
        assert session.id == session_id
        yield {"type": "text_chunk", "text": "Hey! How's your day going?"}
        yield {
            "type": "complete",
            "content": "Hey! How's your day going?",
            "metadata": {"purpose": "live_call_greeting", "transient": True},
        }

    monkeypatch.setattr(character_api, "stream_live_call_greeting_chunks", fake_greeting_stream)

    response = client.post(
        f"/api/chat/sessions/{session_id}/live-call/greeting/stream",
        json={},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0] == {"type": "text_chunk", "text": "Hey! How's your day going?"}
    assert events[1]["metadata"] == {"purpose": "live_call_greeting", "transient": True}
    assert events[-1] == {"type": "done"}
    after = client.get(f"/api/chat/sessions/{session_id}").json()
    assert after["message_count"] == before["message_count"]
    assert after["messages"] == before["messages"]


def test_live_call_runtime_api_returns_404_for_missing_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())

    response = client.get(
        "/api/chat/sessions/chat:missing/live-call/runtime"
    )

    assert response.status_code == 404


def test_live_call_greeting_stream_returns_404_for_missing_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/chat/sessions/chat:missing/live-call/greeting/stream",
        json={},
    )

    assert response.status_code == 404
