from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.gateway.main import create_gateway_app


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    audio = tmp_path / "maya.wav"
    audio.write_bytes(b"RIFF-api-governed-voice")
    manifest = tmp_path / "assets.json"
    SharedAssetStore(manifest).upsert_asset(
        AssetRecord(
            id="voice-cloning:maya",
            owner_id="user:local",
            module="voice-cloning",
            type=AssetType.VOICE_PROFILE,
            mime_type="audio/wav",
            storage_path=str(audio),
            metadata={},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    monkeypatch.setenv("OMNIX_ASSETS_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    return TestClient(create_gateway_app())


def test_governance_api_blocks_link_until_consent_is_granted(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    initial = client.get("/api/voice-profiles/voice-cloning%3Amaya/governance")
    assert initial.status_code == 200
    assert initial.json()["consent_status"] == "unverified"

    blocked = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_voice_asset_id": "voice-cloning:maya",
        },
    )
    assert blocked.status_code == 422
    assert "not granted" in blocked.json()["detail"]

    governed = client.patch(
        "/api/voice-profiles/voice-cloning%3Amaya/governance",
        json={
            "subject_owner": "Maya voice subject",
            "source_type": "user_recording",
            "source_reference": "consent-session:one",
            "creator_id": "user:local",
            "consent_status": "granted",
            "allowed_uses": ["character", "live_call"],
            "deletion_state": "active",
            "deletion_reason": "",
        },
    )
    assert governed.status_code == 200
    assert governed.json()["source_sha256"]
    assert governed.json()["consent_recorded_at"]

    created = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_voice_asset_id": "voice-cloning:maya",
        },
    )
    assert created.status_code == 201
    assert created.json()["default_voice_asset_id"] == "voice-cloning:maya"


def test_deleted_voice_cannot_be_linked(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    governed = client.patch(
        "/api/voice-profiles/voice-cloning%3Amaya/governance",
        json={
            "subject_owner": "Maya voice subject",
            "source_type": "user_recording",
            "source_reference": "consent-session:one",
            "creator_id": "user:local",
            "consent_status": "granted",
            "allowed_uses": ["character", "live_call"],
            "deletion_state": "deleted",
            "deletion_reason": "voice subject requested deletion",
        },
    )
    assert governed.status_code == 200

    response = client.post(
        "/api/characters",
        json={
            "display_name": "Maya",
            "personality_prompt": "Be warm and easygoing.",
            "default_voice_asset_id": "voice-cloning:maya",
        },
    )
    assert response.status_code == 422
    assert "deleted" in response.json()["detail"]
