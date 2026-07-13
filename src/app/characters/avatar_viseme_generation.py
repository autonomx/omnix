"""Generate and persist expanded viseme frames for an existing character avatar pack.

Production batches and jobs use PostgreSQL. Provider-free tests use an in-memory
batch repository; no SQLite schema or connection remains.
"""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.jobs import CreateJobRequest, JobStatus, ResourceClass, default_job_store

from .avatar_models import UpsertCharacterAvatarPackRequest
from .avatar_service import CharacterAvatarService, default_character_avatar_service
from .repository import default_character_db_path
from .service import CharacterService, default_character_service

VisemeGenerationStatus = Literal["generating", "completed", "failed"]

_VISEME_PROMPTS = {
    "A": "open vertical mouth shape used for an ah sound",
    "E": "slightly spread mouth shape used for an ee or eh sound",
    "O": "rounded open mouth shape used for an oh sound",
    "U": "small rounded pursed mouth shape used for an oo sound",
    "MBP": "fully closed lips pressed naturally together for m, b, or p",
    "FV": "upper teeth lightly touching the lower lip for f or v",
    "L": "slightly open mouth with the tongue subtly raised for l",
    "WQ": "small forward rounded lips for w or q",
    "other": "neutral lightly open consonant mouth shape",
}


class CharacterVisemeGenerationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    character_id: str
    status: VisemeGenerationStatus
    job_ids: dict[str, str] = Field(default_factory=dict)
    asset_ids: dict[str, str] = Field(default_factory=dict)
    avatar_pack_version: int | None = None
    error: str = ""
    created_at: str
    updated_at: str


@dataclass
class _State:
    lock: threading.RLock = field(default_factory=threading.RLock)
    batches: dict[str, CharacterVisemeGenerationBatch] = field(default_factory=dict)


_STATES: dict[str, _State] = {}
_STATES_LOCK = threading.RLock()


def _state(path: str | Path | None) -> _State:
    key = str(path or default_character_db_path())
    with _STATES_LOCK:
        return _STATES.setdefault(key, _State())


class CharacterVisemeGenerationRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_character_db_path()
        self._state = _state(db_path)

    def create(self, character_id: str, job_ids: dict[str, str]) -> CharacterVisemeGenerationBatch:
        now = _utcnow()
        batch = CharacterVisemeGenerationBatch(
            id=f"avatar-visemes:{uuid.uuid4().hex}",
            character_id=character_id,
            status="generating",
            job_ids=dict(job_ids),
            created_at=now,
            updated_at=now,
        )
        with self._state.lock:
            self._state.batches[batch.id] = deepcopy(batch)
        return deepcopy(batch)

    def get(self, batch_id: str) -> CharacterVisemeGenerationBatch | None:
        with self._state.lock:
            value = self._state.batches.get(batch_id)
            return deepcopy(value) if value is not None else None

    def list(self, character_id: str) -> list[CharacterVisemeGenerationBatch]:
        with self._state.lock:
            values = [item for item in self._state.batches.values() if item.character_id == character_id]
            values.sort(key=lambda item: (item.created_at, item.id), reverse=True)
            return deepcopy(values)

    def update(
        self,
        batch_id: str,
        *,
        status: VisemeGenerationStatus | None = None,
        job_ids: dict[str, str] | None = None,
        asset_ids: dict[str, str] | None = None,
        avatar_pack_version: int | None = None,
        error: str | None = None,
    ) -> CharacterVisemeGenerationBatch:
        with self._state.lock:
            current = self._state.batches.get(batch_id)
            if current is None:
                raise KeyError(batch_id)
            updated = current.model_copy(
                update={
                    "status": status or current.status,
                    "job_ids": dict(job_ids) if job_ids is not None else current.job_ids,
                    "asset_ids": dict(asset_ids) if asset_ids is not None else current.asset_ids,
                    "avatar_pack_version": avatar_pack_version if avatar_pack_version is not None else current.avatar_pack_version,
                    "error": error if error is not None else current.error,
                    "updated_at": _utcnow(),
                }
            )
            self._state.batches[batch_id] = deepcopy(updated)
            return deepcopy(updated)


class CharacterVisemeGenerationService:
    def __init__(
        self,
        repository: CharacterVisemeGenerationRepository | None = None,
        *,
        character_service: CharacterService | None = None,
        avatar_service: CharacterAvatarService | None = None,
        job_store: Any | None = None,
    ) -> None:
        self.repository = repository or CharacterVisemeGenerationRepository()
        self.character_service = character_service or default_character_service()
        self.avatar_service = avatar_service or default_character_avatar_service()
        self.job_store = job_store or default_job_store()

    def create(self, character_id: str) -> CharacterVisemeGenerationBatch:
        self.character_service.get(character_id)
        self.avatar_service.get(character_id)
        batch = self.repository.create(character_id, {})
        return self.get(batch.id)

    def ensure(self, character_id: str) -> CharacterVisemeGenerationBatch | None:
        pack = self.avatar_service.get(character_id)
        if pack.render_mode == "viseme":
            batches = self.repository.list(character_id)
            return batches[0] if batches else None
        active = next((batch for batch in self.repository.list(character_id) if batch.status == "generating"), None)
        return active or self.create(character_id)

    def reconcile_character(self, character_id: str) -> None:
        for batch in self.repository.list(character_id):
            if batch.status == "generating":
                self.get(batch.id)

    def _create_job(self, batch: CharacterVisemeGenerationBatch, viseme: str, description: str) -> CharacterVisemeGenerationBatch:
        character = self.character_service.get(batch.character_id)
        pack = self.avatar_service.get(batch.character_id)
        reference_asset_id = pack.mouth_frames.get("closed") or pack.base_asset_id
        if not reference_asset_id:
            raise ValueError("character avatar has no canonical portrait")
        job = self.job_store.create_job(
            CreateJobRequest(
                owner_id=f"character:{batch.character_id}",
                module="character-avatar",
                type="image.generate",
                resource_class=ResourceClass.GPU_IMAGE,
                input_payload={
                    "prompt": (
                        f"Using the supplied canonical portrait of {character.display_name}, preserve the exact identity, crop, "
                        f"head position, hair, clothing, lighting, and background. Change only the mouth to a {description}. "
                        "Keep all unrelated details unchanged. No text or watermark."
                    ),
                    "negative_prompt": "text, watermark, face change, hair change, clothing change, camera shift, extra person",
                    "width": 768,
                    "height": 768,
                    "style": "locked character lip-sync frame",
                    "reference_asset_ids": [reference_asset_id],
                    "no_cache": True,
                    "metadata": {"character_id": batch.character_id, "avatar_viseme": viseme},
                },
                compat={"character_id": batch.character_id, "avatar_viseme": viseme},
            )
        )
        return self.repository.update(batch.id, job_ids={**batch.job_ids, viseme: job.id})

    def get(self, batch_id: str) -> CharacterVisemeGenerationBatch:
        batch = self.repository.get(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch.status in {"completed", "failed"}:
            return batch
        assets = dict(batch.asset_ids)
        for viseme, description in _VISEME_PROMPTS.items():
            job_id = batch.job_ids.get(viseme)
            if not job_id:
                return self._create_job(batch, viseme, description)
            job = self.job_store.get_job(job_id)
            if job is None:
                return self.repository.update(batch.id, status="failed", error=f"viseme job missing: {viseme}")
            if job.status in {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.STALE}:
                message = job.error.message if job.error and job.error.message else f"viseme generation failed: {viseme}"
                return self.repository.update(batch.id, status="failed", asset_ids=assets, error=message)
            if job.status != JobStatus.COMPLETED:
                return self.repository.update(batch.id, asset_ids=assets)
            asset_id = next((str(ref.get("asset_id") or "") for ref in job.output_refs if ref.get("asset_id")), "")
            if not asset_id:
                return self.repository.update(batch.id, status="failed", asset_ids=assets, error=f"viseme returned no asset: {viseme}")
            assets[viseme] = asset_id

        current = self.avatar_service.get(batch.character_id)
        mouth_frames = dict(current.mouth_frames)
        mouth_frames.update(assets)
        mouth_frames.setdefault("silence", mouth_frames.get("closed") or current.base_asset_id or "")
        pack = self.avatar_service.upsert(
            batch.character_id,
            UpsertCharacterAvatarPackRequest(
                expected_version=current.version,
                render_mode="viseme",
                renderer=current.renderer,
                rig_asset_id=current.rig_asset_id,
                base_asset_id=current.base_asset_id,
                mouth_frames=mouth_frames,
                blink_frames=current.blink_frames,
                expression_frames=current.expression_frames,
                outfit_frames=current.outfit_frames,
                background_asset_ids=current.background_asset_ids,
                active_outfit=current.active_outfit,
                active_background=current.active_background,
                mouth_anchor=current.mouth_anchor,
            ),
        )
        return self.repository.update(
            batch.id,
            status="completed",
            asset_ids=assets,
            avatar_pack_version=pack.version,
            error="",
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["CharacterVisemeGenerationBatch", "CharacterVisemeGenerationService"]
