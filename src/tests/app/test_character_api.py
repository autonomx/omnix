from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.chat import ChatMessage, default_chat_store
from app.chat.repository import InMemoryChatRepository
from app.gateway.main import create_gateway_app


def _create_maya(client: TestClient) -> None:
    response = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "description": "An easygoing character.",
            "personality_prompt": "Be warm, easygoing, and lightly humorous.",
            "default_greeting": "Hey, good to hear from you.",
            "speech_style": {"speed": 0.94},
        },
    )
    assert response.status_code == 201


def test_character_management_api_is_durable_and_versioned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app())
    _create_maya(client)

    created = client.get("/api/characters/maya").json()
    assert created["id"] == "maya"
    assert created["active_version"] == 1
    assert [item["id"] for item in client.get("/api/characters").json()["characters"]] == ["maya"]

    updated_response = client.patch(
        "/api/characters/maya",
        json={"expected_version": 1, "personality_prompt": "Be calm, warm, curious, and lightly humorous."},
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["active_version"] == 2
    assert client.patch("/api/characters/maya", json={"expected_version": 1, "description": "Stale update"}).status_code == 409
    assert [item["version"] for item in client.get("/api/characters/maya/versions").json()["versions"]] == [2, 1]

    restarted = TestClient(create_gateway_app())
    assert restarted.get("/api/characters/maya").json()["active_version"] == 2


def test_character_archive_is_non_destructive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app())
    _create_maya(client)

    archived = client.delete("/api/characters/maya")
    assert archived.status_code == 200
    assert archived.json()["character"]["status"] == "archived"
    assert client.get("/api/characters/maya").status_code == 404
    assert client.get("/api/characters/maya?include_archived=true").json()["status"] == "archived"


def test_character_api_rejects_non_voice_asset_link(tmp_path: Path, monkeypatch) -> None:
    asset_manifest = tmp_path / "assets.json"
    asset_manifest.write_text(
        """{
  "assets": {
    "image:not-a-voice": {
      "id": "image:not-a-voice",
      "module": "image",
      "type": "image",
      "mime_type": "image/png",
      "storage_path": "missing.png",
      "metadata": {},
      "source_job_id": null,
      "parent_asset_ids": [],
      "derived_asset_ids": [],
      "created_at": "2026-01-01T00:00:00+00:00",
      "compat": {}
    }
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_ASSETS_MANIFEST_PATH", str(asset_manifest))
    client = TestClient(create_gateway_app())
    response = client.post(
        "/api/characters",
        json={
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_voice_asset_id": "image:not-a-voice",
        },
    )
    assert response.status_code == 422
    assert "not a voice profile" in response.json()["detail"]


def test_character_mode_session_uses_server_profile_greeting_and_memory_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.delenv("OMNIX_CHARACTER_MEMORY_ENABLED", raising=False)
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    _create_maya(client)

    created = client.post(
        "/api/chat/sessions",
        json={"title": "Call Maya", "interaction_mode": "character", "character_id": "maya"},
    )
    assert created.status_code == 200
    session = created.json()
    assert session["interaction_mode"] == "character"
    assert session["character_id"] == "maya"
    assert session["read_memory"] is False
    assert session["write_memory"] is False
    assert session["shared_memory_access"] == "none"
    assert session["character_profile_version"] == 1
    assert len(session["effective_identity_hash"]) == 64
    assert session["messages"][0]["content"] == "Hey, good to hear from you."
    assert session["messages"][0]["metadata"]["source"] == "character_profile_greeting"

    stored = client.get(f"/api/chat/sessions/{session['id']}/interaction").json()
    assert stored["character_id"] == "maya"

    store = default_chat_store()
    loaded = store.get_session(session["id"])
    assert loaded is not None
    user_message = ChatMessage(
        id="msg:test-user",
        role="user",
        content="How are you?",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assembly, rendered = store.build_provider_prompt(loaded, user_message)
    identity_text = "\n".join(assembly.assistant_identity)
    assert identity_text == "Be warm, easygoing, and lightly humorous."
    assert assembly.approved_memory == []
    assert rendered.messages[-1].content == "How are you?"


def test_voice_only_system_mode_never_activates_character(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    _create_maya(client)

    created = client.post(
        "/api/chat/sessions",
        json={"interaction_mode": "system", "voice_asset_id": "voice-cloning:maya"},
    ).json()
    assert created["interaction_mode"] == "system"
    assert created["character_id"] is None
    assert created["voice_asset_id"] == "voice-cloning:maya"


def test_session_can_switch_between_system_and_character_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    _create_maya(client)
    session_id = client.post("/api/chat/sessions", json={"title": "Switch test"}).json()["id"]

    character = client.post(
        f"/api/chat/sessions/{session_id}/interaction",
        json={"interaction_mode": "character", "character_id": "maya"},
    )
    assert character.status_code == 200
    assert character.json()["interaction_mode"] == "character"
    assert character.json()["messages"][-1]["content"] == "Hey, good to hear from you."

    system = client.post(
        f"/api/chat/sessions/{session_id}/interaction",
        json={"interaction_mode": "system", "character_id": None},
    )
    assert system.status_code == 200
    assert system.json()["interaction_mode"] == "system"
    assert system.json()["character_id"] is None


def test_character_session_persists_shared_read_only_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_SHARED_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())
    _create_maya(client)
    updated = client.patch(
        "/api/characters/maya",
        json={
            "expected_version": 1,
            "shared_memory_policy": {
                "access": "read_only",
                "allowed_categories": ["fact", "preference"],
            },
        },
    )
    assert updated.status_code == 200

    created = client.post(
        "/api/chat/sessions",
        json={
            "interaction_mode": "character",
            "character_id": "maya",
            "shared_memory_access": "read_only",
        },
    )
    assert created.status_code == 200
    session = created.json()
    assert session["shared_memory_access"] == "read_only"
    first_segment = session["active_segment_id"]

    disabled = client.post(
        f"/api/chat/sessions/{session['id']}/interaction",
        json={
            "interaction_mode": "character",
            "character_id": "maya",
            "shared_memory_access": "none",
        },
    )
    assert disabled.status_code == 200
    assert disabled.json()["shared_memory_access"] == "none"
    assert disabled.json()["active_segment_id"] != first_segment


def test_chat_runtime_repository_does_not_mutate_legacy_sqlite_source(tmp_path: Path) -> None:
    path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat_schema_version(version INTEGER NOT NULL);
            INSERT INTO chat_schema_version(version) VALUES (1);
            CREATE TABLE chat_sessions(
                id TEXT PRIMARY KEY, title TEXT NOT NULL, provider_id TEXT, model_id TEXT,
                research_mode_override TEXT, profile_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                project_id TEXT, memory_enabled INTEGER NOT NULL, memory_snapshot_id TEXT,
                memory_snapshot_revision INTEGER, memory_record_count INTEGER NOT NULL,
                memory_last_refreshed_at TEXT, message_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE chat_messages(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, position INTEGER NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL, UNIQUE(session_id, position)
            );
            CREATE TABLE chat_session_metadata(session_id TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY(session_id,key));
            CREATE TABLE chat_import_state(source_path TEXT PRIMARY KEY, source_hash TEXT NOT NULL, status TEXT NOT NULL, imported_session_count INTEGER NOT NULL, imported_message_count INTEGER NOT NULL, skipped_session_count INTEGER NOT NULL, errors_json TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
        )

    repository = InMemoryChatRepository(path)
    assert repository.load_sessions() == []

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chat_sessions)")}
        version = connection.execute("SELECT version FROM chat_schema_version").fetchone()[0]
    assert version == 1
    assert "interaction_mode" not in columns
