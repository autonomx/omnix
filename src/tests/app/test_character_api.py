from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def test_character_management_api_is_durable_and_versioned(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app())

    created_response = client.post(
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
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["id"] == "maya"
    assert created["active_version"] == 1

    listed = client.get("/api/characters").json()["characters"]
    assert [item["id"] for item in listed] == ["maya"]

    updated_response = client.patch(
        "/api/characters/maya",
        json={
            "expected_version": 1,
            "personality_prompt": "Be calm, warm, curious, and lightly humorous.",
        },
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["active_version"] == 2

    stale_response = client.patch(
        "/api/characters/maya",
        json={"expected_version": 1, "description": "Stale update"},
    )
    assert stale_response.status_code == 409

    versions = client.get("/api/characters/maya/versions").json()["versions"]
    assert [item["version"] for item in versions] == [2, 1]

    restarted = TestClient(create_gateway_app())
    loaded = restarted.get("/api/characters/maya")
    assert loaded.status_code == 200
    assert loaded.json()["active_version"] == 2


def test_character_archive_is_non_destructive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app())
    client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
        },
    )

    archived = client.delete("/api/characters/maya")

    assert archived.status_code == 200
    assert archived.json()["character"]["status"] == "archived"
    assert client.get("/api/characters/maya").status_code == 404
    included = client.get("/api/characters/maya?include_archived=true")
    assert included.status_code == 200
    assert included.json()["status"] == "archived"


def test_character_api_rejects_non_voice_asset_link(tmp_path: Path, monkeypatch) -> None:
    character_db = tmp_path / "characters.sqlite3"
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
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(character_db))
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
