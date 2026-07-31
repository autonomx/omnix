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
from app.jobs import CompleteJobRequest, FailJobRequest
from app.testing.in_memory_job_store import InMemoryJobStore


def _complete_image_job(
    tmp_path: Path,
    jobs: InMemoryJobStore,
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


def _build_viseme_service(tmp_path: Path, monkeypatch):
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
    character_service = CharacterService(
        characters,
        asset_store_factory=lambda: assets,
    )
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
            mouth_anchor={"x": 0.5, "y": 0.61, "width": 0.3, "height": 0.17},
        ),
    )
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite3")
    service = CharacterVisemeGenerationService(
        CharacterVisemeGenerationRepository(database),
        character_service=character_service,
        avatar_service=avatar_service,
        job_store=jobs,
    )
    return service, jobs, assets, avatar_service


def test_viseme_generation_builds_four_conservative_phases_per_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, jobs, assets, avatar_service = _build_viseme_service(
        tmp_path,
        monkeypatch,
    )

    batch = service.create("maya")
    assert batch.status == "generating"
    assert list(batch.job_ids) == ["A_soft", "A_medium"]
    assert batch.attempts == {"A_soft": 1, "A_medium": 1}
    first_job = jobs.get_job(batch.job_ids["A_soft"])
    assert first_job is not None
    assert first_job.input_payload["metadata"][
        "avatar_viseme_articulation_percent"
    ] == 15
    assert "ordinary quiet conversational speech" in first_job.input_payload["prompt"]
    assert "exaggerated open mouth" in first_job.input_payload["negative_prompt"]

    completed: set[str] = set()
    while batch.status != "completed":
        pending = [
            (frame_key, job_id)
            for frame_key, job_id in batch.job_ids.items()
            if frame_key not in completed
        ]
        assert 1 <= len(pending) <= 2
        for frame_key, job_id in pending:
            _complete_image_job(
                tmp_path,
                jobs,
                assets,
                job_id,
                f"maya-viseme-{frame_key.lower()}",
            )
            completed.add(frame_key)
        batch = service.get(batch.id)

    assert batch.status == "completed"
    assert batch.avatar_pack_version == 2
    assert len(batch.asset_ids) == 36
    assert not batch.quality_fallbacks
    pack = avatar_service.get("maya")
    assert pack.render_mode == "viseme"
    assert pack.renderer == "sprite"
    assert pack.mouth_frames["A_soft"] == "image:maya-viseme-a_soft"
    assert pack.mouth_frames["A_medium"] == "image:maya-viseme-a_medium"
    assert pack.mouth_frames["A_strong"] == "image:maya-viseme-a_strong"
    assert pack.mouth_frames["A"] == "image:maya-viseme-a"
    assert pack.mouth_frames["MBP_soft"] == "image:maya-viseme-mbp_soft"
    assert pack.mouth_frames["MBP"] == "image:maya-viseme-mbp"
    assert pack.mouth_frames["silence"] == "image:maya-closed"
    assert pack.expression_frames["listening"] == "image:maya-closed"
    assert "A_35" not in pack.mouth_frames


def test_rejected_viseme_is_retried_then_falls_back_to_closed_frame(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, jobs, _assets, _avatar_service = _build_viseme_service(
        tmp_path,
        monkeypatch,
    )
    batch = service.create("maya")
    first_job_id = batch.job_ids["A_soft"]

    for expected_attempt in (2, 3):
        jobs.mark_running(first_job_id)
        jobs.fail_job(
            first_job_id,
            FailJobRequest(
                code="avatar_frame_quality_rejected",
                message="avatar_frame_quality_rejected:dark_delta=0.5",
                retryable=True,
            ),
        )
        batch = service.get(batch.id)
        retry_job_id = batch.job_ids["A_soft"]
        assert retry_job_id != first_job_id
        assert batch.attempts["A_soft"] == expected_attempt
        retry_job = jobs.get_job(retry_job_id)
        assert retry_job is not None
        assert "substantially subtler" in retry_job.input_payload["prompt"]
        first_job_id = retry_job_id

    jobs.mark_running(first_job_id)
    jobs.fail_job(
        first_job_id,
        FailJobRequest(
            code="avatar_frame_quality_rejected",
            message="avatar_frame_quality_rejected:dark_delta=0.5",
            retryable=True,
        ),
    )
    batch = service.get(batch.id)

    assert batch.status == "generating"
    assert batch.asset_ids["A_soft"] == "image:maya-closed"
    assert batch.quality_fallbacks["A_soft"] == "image:maya-closed"
    assert batch.attempts["A_soft"] == 3


def test_avatar_runtime_repository_does_not_mutate_legacy_sqlite_source(
    tmp_path: Path,
) -> None:
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
                "maya",
                1,
                "audio_envelope",
                "image:maya",
                '{"closed":"image:maya"}',
                "{}",
                "{}",
                "{}",
                "{}",
                None,
                None,
                "{}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    repository = CharacterAvatarRepository(database)
    assert repository.get("maya") is None

    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(character_avatar_packs)"
            )
        }
        row_count = connection.execute(
            "SELECT COUNT(*) FROM character_avatar_packs"
        ).fetchone()[0]
    assert row_count == 1
    assert "renderer" not in columns
    assert "rig_asset_id" not in columns
