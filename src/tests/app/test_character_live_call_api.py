from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def test_live_call_runtime_api_resolves_character_without_browser_prompt_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())

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
    session_id = created_session.json()["id"]

    response = client.get(
        f"/api/chat/sessions/{session_id}/live-call/runtime"
    )

    assert response.status_code == 200
    runtime = response.json()
    assert runtime["interaction_mode"] == "character"
    assert runtime["character_id"] == "maya"
    assert runtime["display_name"] == "Maya"
    assert runtime["greeting"] == "Hey, good to hear from you."
    assert runtime["speech_style"]["speed"] == 0.94
    assert runtime["speech_style"]["emotion"] == "calm"
    assert runtime["character_profile_version"] == 1
    assert len(runtime["effective_identity_hash"]) == 64
    assert runtime["preload"]["profile_loaded"] is True


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
