from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.characters.live_call import resolve_live_call_runtime
from app.characters.service import CharacterService, CharacterVoiceAssetError
from app.characters.voice_consent import (
    UpdateVoiceProfileGovernanceRequest,
    VoiceConsentError,
    VoiceProfileGovernanceService,
)
from app.chat import CreateChatSessionRequest, default_chat_store


def _voice_store(tmp_path: Path) -> tuple[SharedAssetStore, Path]:
    audio = tmp_path / "maya.wav"
    audio.write_bytes(b"RIFF-governed-voice")
    store = SharedAssetStore(tmp_path / "assets.json")
    store.upsert_asset(
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
    return store, audio


def _grant(
    service: VoiceProfileGovernanceService,
    *,
    uses: list[str],
    status: str = "granted",
    deletion_state: str = "active",
):
    return service.update(
        "voice-cloning:maya",
        UpdateVoiceProfileGovernanceRequest(
            subject_owner="Maya voice subject",
            source_type="user_recording",
            source_reference="consent-session:one",
            creator_id="user:local",
            consent_status=status,
            allowed_uses=uses,
            deletion_state=deletion_state,
            deletion_reason="revoked by voice subject" if deletion_state != "active" else "",
        ),
    )


def test_governance_defaults_unverified_and_persists_hash(tmp_path: Path) -> None:
    store, audio = _voice_store(tmp_path)
    service = VoiceProfileGovernanceService(asset_store_factory=lambda: store)

    initial = service.get("voice-cloning:maya")
    assert initial.consent_status == "unverified"
    assert initial.allowed_uses == []
    assert initial.source_sha256 == hashlib.sha256(audio.read_bytes()).hexdigest()

    updated = _grant(service, uses=["character", "live_call"])
    restarted = VoiceProfileGovernanceService(
        asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets.json")
    ).get("voice-cloning:maya")
    assert restarted == updated
    assert restarted.consent_recorded_at is not None


def test_allowed_use_and_revocation_are_enforced(tmp_path: Path) -> None:
    store, _ = _voice_store(tmp_path)
    service = VoiceProfileGovernanceService(asset_store_factory=lambda: store)
    _grant(service, uses=["character"])

    service.validate_use("voice-cloning:maya", "character")
    with pytest.raises(VoiceConsentError, match="live_call"):
        service.validate_use("voice-cloning:maya", "live_call")

    _grant(service, uses=["character", "live_call"], status="revoked")
    with pytest.raises(VoiceConsentError, match="revoked"):
        service.validate_use("voice-cloning:maya", "character")


def test_character_link_rejects_unverified_voice_then_accepts_governed_voice(tmp_path: Path) -> None:
    store, _ = _voice_store(tmp_path)
    characters = CharacterService(
        CharacterRepository(tmp_path / "characters.sqlite3"),
        asset_store_factory=lambda: store,
    )
    request = CreateCharacterRequest(
        id="maya",
        display_name="Maya",
        personality_prompt="Be warm and easygoing.",
        default_voice_asset_id="voice-cloning:maya",
    )

    with pytest.raises(CharacterVoiceAssetError, match="not granted"):
        characters.create(request)

    _grant(
        VoiceProfileGovernanceService(asset_store_factory=lambda: store),
        uses=["character", "live_call"],
    )
    created = characters.create(request)
    assert created.default_voice_asset_id == "voice-cloning:maya"


def test_live_call_rejects_voice_without_live_call_permission(tmp_path: Path, monkeypatch) -> None:
    store, _ = _voice_store(tmp_path)
    governance = VoiceProfileGovernanceService(asset_store_factory=lambda: store)
    _grant(governance, uses=["character"])
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    repository.create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and easygoing.",
            default_voice_asset_id="voice-cloning:maya",
        )
    )
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    chat = default_chat_store()
    session = chat.create_session(CreateChatSessionRequest(title="Maya call"))
    session = chat.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(interaction_mode="character", character_id="maya"),
    )
    assert session is not None
    characters = CharacterService(repository, asset_store_factory=lambda: store)

    with pytest.raises(CharacterVoiceAssetError, match="live_call"):
        resolve_live_call_runtime(session, character_service_factory=lambda: characters)

    _grant(governance, uses=["character", "live_call"])
    runtime = resolve_live_call_runtime(session, character_service_factory=lambda: characters)
    assert runtime.voice_asset_id == "voice-cloning:maya"
