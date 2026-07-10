from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest
from app.characters.avatar_generation_models import (
    BackfillClonedVoiceCharactersRequest,
    CreateCharacterAvatarGenerationRequest,
)
from app.characters.avatar_generation_repository import CharacterAvatarGenerationRepository
from app.characters.avatar_generation_service import CharacterAvatarGenerationService
from app.characters.avatar_repository import CharacterAvatarRepository
from app.characters.avatar_service import CharacterAvatarService
from app.characters.service import CharacterService
from app.characters.voice_consent import (
    UpdateVoiceProfileGovernanceRequest,
    VoiceProfileGovernanceService,
)
from app.jobs import CompleteJobRequest, SQLiteJobStore


def _runtime(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    character_repository = CharacterRepository(tmp_path / "characters.sqlite3")
    assets = SharedAssetStore(tmp_path / "assets.json")
    character_service = CharacterService(character_repository, asset_store_factory=lambda: assets)
    avatar_service = CharacterAvatarService(
        CharacterAvatarRepository(tmp_path / "characters.sqlite3"),
        character_service_factory=lambda: character_service,
        asset_store_factory=lambda: assets,
    )
    jobs = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    generation_service = CharacterAvatarGenerationService(
        CharacterAvatarGenerationRepository(tmp_path / "characters.sqlite3"),
        character_service_factory=lambda: character_service,
        avatar_service_factory=lambda: avatar_service,
        job_store_factory=lambda: jobs,
        asset_store_factory=lambda: assets,
    )
    return character_service, avatar_service, generation_service, jobs, assets


def _complete_image_job(
    tmp_path: Path,
    jobs: SQLiteJobStore,
    assets: SharedAssetStore,
    job_id: str,
    name: str,
) -> str:
    path = tmp_path / f"{name}.png"
    path.write_bytes(b"PNG")
    asset_id = f"image:{name}"
    assets.upsert_asset(
        AssetRecord(
            id=asset_id,
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(path),
            source_job_id=job_id,
            metadata={"immutable": True},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    jobs.mark_running(job_id)
    jobs.complete_job(
        job_id,
        CompleteJobRequest(
            output_refs=[
                {
                    "type": "image",
                    "asset_id": asset_id,
                    "title": name,
                    "mime_type": "image/png",
                    "width": 768,
                    "height": 768,
                    "provider_id": "",
                }
            ]
        ),
    )
    return asset_id


def _uploaded_source(tmp_path: Path, assets: SharedAssetStore, name: str = "user-face") -> str:
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (320, 400), (120, 90, 80)).save(path, format="PNG")
    asset_id = f"image-reference:{name}"
    assets.upsert_asset(
        AssetRecord(
            id=asset_id,
            module="image-reference",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(path),
            metadata={"reference_upload": True, "filename": path.name},
            created_at="2026-01-01T00:00:00+00:00",
            compat={"uploaded_reference": True},
        )
    )
    return asset_id


def test_generation_reconciles_base_variants_and_avatar_pack(tmp_path: Path, monkeypatch) -> None:
    characters, avatars, generations, jobs, assets = _runtime(tmp_path, monkeypatch)
    characters.create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and conversational.",
        )
    )
    batch = generations.create(
        "maya",
        CreateCharacterAvatarGenerationRequest(
            appearance_prompt="Silver hair and a moonlit blue outfit.",
            include_outfit=False,
            include_background=False,
        ),
    )
    assert batch.status == "generating_base"
    _complete_image_job(tmp_path, jobs, assets, batch.base_job_id, "maya-base")

    batch = generations.get(batch.id)
    assert batch.status == "generating_variants"
    assert {"mouth_small", "mouth_medium", "mouth_wide", "blink_closed"}.issubset(batch.variant_job_ids)
    for variant, job_id in batch.variant_job_ids.items():
        _complete_image_job(tmp_path, jobs, assets, job_id, f"maya-{variant}")

    batch = generations.get(batch.id)
    assert batch.status == "completed"
    assert batch.avatar_pack_version == 1
    pack = avatars.get("maya")
    assert pack.mouth_frames["closed"] == "image:maya-base"
    assert pack.mouth_frames["wide"] == "image:maya-mouth_wide"
    assert pack.blink_frames["closed"] == "image:maya-blink_closed"
    assert pack.expression_frames["thinking"] == "image:maya-expression_thinking"


def test_uploaded_image_is_governed_and_used_as_base_reference(tmp_path: Path, monkeypatch) -> None:
    characters, avatars, generations, jobs, assets = _runtime(tmp_path, monkeypatch)
    characters.create(
        CreateCharacterRequest(
            id="self-avatar",
            display_name="My Avatar",
            personality_prompt="Be a conversational companion.",
        )
    )
    source_asset_id = _uploaded_source(tmp_path, assets)

    batch = generations.create(
        "self-avatar",
        CreateCharacterAvatarGenerationRequest(
            source_asset_id=source_asset_id,
            source_image_consent_confirmed=True,
            style="faithful photographic portrait",
            include_outfit=False,
            include_background=False,
        ),
    )

    base_job = jobs.get_job(batch.base_job_id)
    assert base_job is not None
    assert base_job.input_payload["reference_asset_ids"] == [source_asset_id]
    assert base_job.input_payload["no_cache"] is True
    assert base_job.input_payload["metadata"]["source_asset_id"] == source_asset_id
    source = next(asset for asset in assets.list_assets().assets if asset.id == source_asset_id)
    assert source.owner_id == "user:local"
    assert source.metadata["source_image_consent_confirmed"] is True
    assert source.metadata["linked_character_ids"] == ["self-avatar"]

    _complete_image_job(tmp_path, jobs, assets, batch.base_job_id, "self-avatar-base")
    batch = generations.get(batch.id)
    for variant, job_id in batch.variant_job_ids.items():
        _complete_image_job(tmp_path, jobs, assets, job_id, f"self-avatar-{variant}")
    batch = generations.get(batch.id)

    assert batch.status == "completed"
    pack = avatars.get("self-avatar")
    assert pack.base_asset_id == "image:self-avatar-base"
    assert pack.mouth_frames["closed"] == "image:self-avatar-base"
    assert pack.mouth_frames["wide"] == "image:self-avatar-mouth_wide"


def test_uploaded_image_requires_rights_confirmation(tmp_path: Path, monkeypatch) -> None:
    characters, _, generations, _, assets = _runtime(tmp_path, monkeypatch)
    characters.create(
        CreateCharacterRequest(
            id="self-avatar",
            display_name="My Avatar",
            personality_prompt="Be a conversational companion.",
        )
    )
    source_asset_id = _uploaded_source(tmp_path, assets)

    with pytest.raises(ValueError, match="avatar_source_consent_required"):
        generations.create(
            "self-avatar",
            CreateCharacterAvatarGenerationRequest(source_asset_id=source_asset_id),
        )


def test_governed_voice_backfill_creates_profiles_and_skips_reference_voice(tmp_path: Path, monkeypatch) -> None:
    characters, _, generations, _, assets = _runtime(tmp_path, monkeypatch)
    governance = VoiceProfileGovernanceService(asset_store_factory=lambda: assets)
    for name in ("Maya", "default_ref"):
        path = tmp_path / f"{name}.wav"
        path.write_bytes(f"RIFF-{name}".encode())
        asset_id = f"voice-cloning:{name}"
        assets.upsert_asset(
            AssetRecord(
                id=asset_id,
                owner_id="user:local",
                module="voice-cloning",
                type=AssetType.VOICE_PROFILE,
                mime_type="audio/wav",
                storage_path=str(path),
                metadata={"title": name},
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        governance.update(
            asset_id,
            UpdateVoiceProfileGovernanceRequest(
                subject_owner=f"{name} voice subject",
                source_type="local_recording",
                creator_id="user:local",
                consent_status="granted",
                allowed_uses=["character", "live_call"],
                deletion_state="active",
            ),
        )

    response = generations.backfill_cloned_voices(
        BackfillClonedVoiceCharactersRequest(queue_avatar_generation=False)
    )
    maya = next(item for item in response.items if item.display_name == "Maya")
    reference = next(item for item in response.items if item.display_name == "default_ref")
    assert maya.result == "created"
    assert characters.get(maya.character_id or "").default_voice_asset_id == "voice-cloning:Maya"
    assert reference.result == "skipped"
