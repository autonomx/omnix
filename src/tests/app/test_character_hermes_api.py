from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_MEMORY_DIR", str(tmp_path / "hermes-characters"))
    client = TestClient(create_gateway_app())
    created = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
        },
    )
    assert created.status_code == 201
    return client


def test_character_hermes_api_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.delenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", raising=False)

    imported = client.post("/api/characters/maya/hermes/import")
    exported = client.post("/api/characters/maya/hermes/export")

    assert imported.status_code == 200
    assert imported.json()["enabled"] is False
    assert imported.json()["character_id"] == "maya"
    assert imported.json()["skipped_reasons"] == ["character_sync_disabled"]
    assert exported.status_code == 200
    assert exported.json()["skipped_reasons"] == ["character_sync_disabled"]


def test_character_hermes_api_imports_pending_candidates_only(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    root = tmp_path / "hermes-characters" / "maya"
    root.mkdir(parents=True)
    (root / "CHARACTER.md").write_text(
        "# Relationship notes\n- The user enjoys quiet evening calls\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", "1")

    response = client.post("/api/characters/maya/hermes/import")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["available"] is True
    assert len(payload["imported_candidate_ids"]) == 1


def test_character_hermes_api_requires_existing_explicit_character(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", "1")

    response = client.post("/api/characters/unknown/hermes/export")

    assert response.status_code == 404
