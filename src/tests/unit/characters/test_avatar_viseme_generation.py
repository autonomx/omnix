from __future__ import annotations

import sqlite3
from pathlib import Path

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest
from app.characters.avatar_models import UpsertCharacterAvatarPackRequest
from app.characters.avatar_repository import CharacterAvatarRepository
from app.characters.avatar_service import CharacterAvatarService
from app.characters.avatar_viseme_generation import (
    CharacterVisemeGenerationRepository,
    CharacterVisemeGenerationService,
)
from app.characters.service import CharacterService
from app.jobs import CompleteJobRequest, SQLiteJobStore


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


def test_viseme_generation_upgrades_existing_pack_and_preserves_fallbacks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    database = tmp_path / "characters.sqlite3"
    assets = SharedAssetStore(tmp_path / "assets.json")
    closed_path = tmp_path / "maya-closed.png"
    closed_path.write_bytes(b"PNG")
    assets.upsert_asset(
        AssetRecord(
            id="image:maya-closed",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(closed_path),
            metadata={"immutable": True},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    characters = CharacterRepository(database)
    characters.create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and conversational.",
        )
    )
    character_service = CharacterService(characters, asset_store_factory=lambda: assets)
    avatar_service = CharacterAvatarService(
        CharacterAvatarRepository(database),
        character_service_factory=lambda: character_service,
        asset_store_factory=lambda: assets,
    )
    avatar_service.upsert(
        "maya",
        UpsertCharacterAvatarPackRequest(
            render_mode="audio_envelope",
            base_asset_id="image:maya-closed",
            mouth_frames={
                "closed": "image:maya-closed",
                "small": "image:maya-closed",
                "medium": "image:maya-closed",
                "wide": "image:maya-closed",
            },
            expression_frames={"listening": "image:maya-closed"},
        ),
    )
    jobs = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    service = CharacterVisemeGenerationService(
        CharacterVisemeGenerationRepository(database),
        character_service=character_service,
        avatar_service=avatar_service,
        job_store=jobs,
    )

    batch = service.create("maya")
    assert batch.status == "generating"
    assert {"A", "E", "O", "U", "MBP", "FV", "L", "WQ", "other"} == set(batch.job_ids)
    for viseme, job_id in batch.job_ids.items():
        _complete_image_job(tmp_path, jobs, assets, job_id, f"maya-viseme-{viseme.lower()}")

    batch = service.get(batch.id)
    assert batch.status == "completed"
    assert batch.avatar_pack_version == 2
    pack = avatar_service.get("maya")
    assert pack.render_mode == "viseme"
    assert pack.renderer == "sprite"
    assert pack.mouth_frames["A"] == "image:maya-viseme-a"
    assert pack.mouth_frames["MBP"] == "image:maya-viseme-mbp"
    assert pack.mouth_frames["silence"] == "image:maya-closed"
    assert pack.expression_frames["listening"] == "image:maya-closed"


def test_avatar_repository_migrates_renderer_columns_without_data_loss(tmp_path: Path) -> None:
    database = tmp_path / "characters.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE character_avatar_packs (
                character_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                render_mode TEXT NOT NULL,
                base_asset_id TEXT,
                mouth_frames_json TEXT NOT NULL,
                blink_frames_json TEXT NOT NULL,
                expression_frames_json TEXT NOT NULL,
                outfit_frames_json TEXT NOT NULL,
                background_asset_ids_json TEXT NOT NULL,
                active_outfit TEXT,
                active_background TEXT,
                mouth_anchor_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO character_avatar_packs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "maya", 1, "audio_envelope", "image:maya", '{"closed":"image:maya"}',
                "{}", "{}", "{}", "{}", None, None, "{}",
                "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
            ),
        )
    repository = CharacterAvatarRepository(database)
    pack = repository.get("maya")
    assert pack is not None
    assert pack.renderer == "sprite"
    assert pack.rig_asset_id is None
    assert pack.mouth_frames["closed"] == "image:maya"
