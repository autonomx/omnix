from __future__ import annotations

import hashlib
from pathlib import Path

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest
from app.characters.service import CharacterService
from app.characters.voice_consent import (
    ALL_VOICE_USES,
    UpdateVoiceProfileGovernanceRequest,
    VoiceProfileGovernanceService,
)
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
# Shares the fixed 'maya' character; serialize on one xdist worker.
pytestmark = [pytest.mark.postgres, pytest.mark.xdist_group("characters-maya")]


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


def _update_legacy_governance(
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
            deletion_reason="legacy state" if deletion_state != "active" else "",
        ),
    )


def test_governance_defaults_granted_active_for_all_uses_and_persists_hash(tmp_path: Path) -> None:
    store, audio = _voice_store(tmp_path)
    service = VoiceProfileGovernanceService(asset_store_factory=lambda: store)

    initial = service.get("voice-cloning:maya")
    assert initial.consent_status == "granted"
    assert initial.deletion_state == "active"
    assert initial.allowed_uses == list(ALL_VOICE_USES)
    assert initial.subject_owner == "user:local"
    assert initial.creator_id == "user:local"
    assert initial.source_sha256 == hashlib.sha256(audio.read_bytes()).hexdigest()

    updated = _update_legacy_governance(
        service,
        uses=["character"],
        status="revoked",
        deletion_state="deleted",
    )
    restarted = VoiceProfileGovernanceService(
        asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets.json")
    ).get("voice-cloning:maya")
    assert restarted == updated
    assert restarted.consent_status == "granted"
    assert restarted.deletion_state == "active"
    assert restarted.allowed_uses == list(ALL_VOICE_USES)
    assert restarted.consent_recorded_at is not None


def test_every_supported_use_is_automatically_available(tmp_path: Path) -> None:
    store, _ = _voice_store(tmp_path)
    service = VoiceProfileGovernanceService(asset_store_factory=lambda: store)
    _update_legacy_governance(
        service,
        uses=["character"],
        status="revoked",
        deletion_state="deleted",
    )

    for use in ALL_VOICE_USES:
        governance = service.validate_use("voice-cloning:maya", use)
        assert governance.consent_status == "granted"
        assert governance.deletion_state == "active"
        assert use in governance.allowed_uses


def test_character_link_accepts_cloned_voice_without_manual_governance(tmp_path: Path) -> None:
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

    created = characters.create(request)
    assert created.default_voice_asset_id == "voice-cloning:maya"


