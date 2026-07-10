"""SQLite persistence for multi-job Character avatar generation batches."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .avatar_generation_models import (
    AvatarGenerationStatus,
    CharacterAvatarGenerationBatch,
    CreateCharacterAvatarGenerationRequest,
)
from .repository import default_character_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_avatar_generation_batches (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json TEXT NOT NULL,
    base_job_id TEXT NOT NULL,
    variant_job_ids_json TEXT NOT NULL,
    asset_ids_json TEXT NOT NULL,
    avatar_pack_version INTEGER,
    error TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_character_avatar_batches_character_created
ON character_avatar_generation_batches(character_id, created_at DESC, id DESC);
"""


class CharacterAvatarGenerationRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_character_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def create(
        self,
        character_id: str,
        request: CreateCharacterAvatarGenerationRequest,
        base_job_id: str,
    ) -> CharacterAvatarGenerationBatch:
        now = _utcnow()
        batch = CharacterAvatarGenerationBatch(
            id=f"avatar-generation:{uuid.uuid4().hex}",
            character_id=character_id,
            status="generating_base",
            request=request,
            base_job_id=base_job_id,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO character_avatar_generation_batches(
                    id, character_id, status, request_json, base_job_id,
                    variant_job_ids_json, asset_ids_json, avatar_pack_version,
                    error, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                _batch_values(batch),
            )
        return batch

    def get(self, batch_id: str) -> CharacterAvatarGenerationBatch | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM character_avatar_generation_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        return _row_to_batch(row) if row else None

    def list(self, character_id: str) -> list[CharacterAvatarGenerationBatch]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM character_avatar_generation_batches
                WHERE character_id = ? ORDER BY created_at DESC, id DESC
                """,
                (character_id,),
            ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def update(
        self,
        batch_id: str,
        *,
        status: AvatarGenerationStatus | None = None,
        variant_job_ids: dict[str, str] | None = None,
        asset_ids: dict[str, str] | None = None,
        avatar_pack_version: int | None = None,
        error: str | None = None,
    ) -> CharacterAvatarGenerationBatch:
        current = self.get(batch_id)
        if current is None:
            raise KeyError(batch_id)
        updated = current.model_copy(
            update={
                "status": status or current.status,
                "variant_job_ids": dict(variant_job_ids) if variant_job_ids is not None else current.variant_job_ids,
                "asset_ids": dict(asset_ids) if asset_ids is not None else current.asset_ids,
                "avatar_pack_version": avatar_pack_version if avatar_pack_version is not None else current.avatar_pack_version,
                "error": error if error is not None else current.error,
                "updated_at": _utcnow(),
            }
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE character_avatar_generation_batches SET
                    status = ?, request_json = ?, base_job_id = ?,
                    variant_job_ids_json = ?, asset_ids_json = ?,
                    avatar_pack_version = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    _json(updated.request.model_dump(mode="json")),
                    updated.base_job_id,
                    _json(updated.variant_job_ids),
                    _json(updated.asset_ids),
                    updated.avatar_pack_version,
                    updated.error,
                    updated.updated_at,
                    updated.id,
                ),
            )
        return updated


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _batch_values(batch: CharacterAvatarGenerationBatch) -> tuple[Any, ...]:
    return (
        batch.id,
        batch.character_id,
        batch.status,
        _json(batch.request.model_dump(mode="json")),
        batch.base_job_id,
        _json(batch.variant_job_ids),
        _json(batch.asset_ids),
        batch.avatar_pack_version,
        batch.error,
        batch.created_at,
        batch.updated_at,
    )


def _row_to_batch(row: sqlite3.Row) -> CharacterAvatarGenerationBatch:
    return CharacterAvatarGenerationBatch(
        id=row["id"],
        character_id=row["character_id"],
        status=row["status"],
        request=CreateCharacterAvatarGenerationRequest.model_validate(
            json.loads(row["request_json"] or "{}")
        ),
        base_job_id=row["base_job_id"],
        variant_job_ids=json.loads(row["variant_job_ids_json"] or "{}"),
        asset_ids=json.loads(row["asset_ids_json"] or "{}"),
        avatar_pack_version=row["avatar_pack_version"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = ["CharacterAvatarGenerationRepository"]
