from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def test_character_data_export_and_confirmed_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))
    client = TestClient(create_gateway_app())
    created = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_greeting": "Hey.",
        },
    )
    assert created.status_code == 201

    exported = client.get("/api/characters/maya/data")
    assert exported.status_code == 200
    assert exported.json()["character"]["id"] == "maya"
    assert exported.json()["versions"][0]["version"] == 1

    mismatch = client.post(
        "/api/characters/maya/data/actions",
        json={"confirm_character_id": "other", "archive_profile": True},
    )
    assert mismatch.status_code == 409

    archived = client.post(
        "/api/characters/maya/data/actions",
        json={"confirm_character_id": "maya", "archive_profile": True},
    )
    assert archived.status_code == 200
    assert archived.json()["profile_archived"] is True
    after = client.get("/api/characters/maya/data")
    assert after.status_code == 200
    assert after.json()["character"]["status"] == "archived"
