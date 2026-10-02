"""PostgreSQL-backed avatar generation batch repositories."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.characters.avatar_generation_models import (
    CharacterAvatarGenerationBatch,
    CreateCharacterAvatarGenerationRequest,
)
from app.characters.avatar_viseme_generation import CharacterVisemeGenerationBatch
from app.persistence.database import PostgresDatabase, default_database
from app.security.tenant_context import RequestTenant


_MODULE = "character-avatar"
_AVATAR_BATCH_TYPE = "generation-batch"
_VISEME_BATCH_TYPE = "viseme-generation-batch"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresCharacterAvatarGenerationRepositoryAdapter:
    """Persist avatar generation batch state in tenant-scoped module records."""
    context = RequestTenant()

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        self.context = None  # follows the request tenant

    def create(
        self,
        character_id: str,
        request: CreateCharacterAvatarGenerationRequest,
        base_job_id: str,
    ) -> CharacterAvatarGenerationBatch:
        batch = CharacterAvatarGenerationBatch(
            id=f"avatar-generation:{uuid.uuid4().hex}",
            character_id=character_id,
            status="generating_base",
            request=request,
            base_job_id=base_job_id,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        with self.database.transaction() as connection:
            self._write(connection, _AVATAR_BATCH_TYPE, batch.id, batch)
        return batch

    def get(self, batch_id: str) -> CharacterAvatarGenerationBatch | None:
        payload = self._get(_AVATAR_BATCH_TYPE, batch_id)
        return CharacterAvatarGenerationBatch.model_validate(payload) if payload else None

    def list(self, character_id: str) -> list[CharacterAvatarGenerationBatch]:
        payloads = self._list(_AVATAR_BATCH_TYPE, character_id)
        return [CharacterAvatarGenerationBatch.model_validate(item) for item in payloads]

    def update(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        variant_job_ids: dict[str, str] | None = None,
        asset_ids: dict[str, str] | None = None,
        avatar_pack_version: int | None = None,
        error: str | None = None,
    ) -> CharacterAvatarGenerationBatch:
        with self.database.transaction() as connection:
            current = self._locked_get(connection, _AVATAR_BATCH_TYPE, batch_id)
            if current is None:
                raise KeyError(batch_id)
            updated = CharacterAvatarGenerationBatch.model_validate(current).model_copy(
                update={
                    "status": status or current["status"],
                    "variant_job_ids": (
                        dict(variant_job_ids)
                        if variant_job_ids is not None
                        else current.get("variant_job_ids", {})
                    ),
                    "asset_ids": dict(asset_ids) if asset_ids is not None else current.get("asset_ids", {}),
                    "avatar_pack_version": (
                        avatar_pack_version
                        if avatar_pack_version is not None
                        else current.get("avatar_pack_version")
                    ),
                    "error": error if error is not None else current.get("error", ""),
                    "updated_at": _utcnow(),
                }
            )
            self._write(connection, _AVATAR_BATCH_TYPE, batch_id, updated)
        return updated

    def _get(self, record_type: str, record_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND status = 'active'
                """,
                (self.context.workspace_id, _MODULE, record_type, record_id),
            ).fetchone()
        return dict(row[0]) if row is not None else None

    def _list(self, record_type: str, character_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND status = 'active' AND payload->>'character_id' = %s
                 ORDER BY payload->>'created_at' DESC, record_id DESC
                 LIMIT 200
                """,
                (self.context.workspace_id, _MODULE, record_type, character_id),
            ).fetchall()
        return [dict(row[0]) for row in rows]

    def _locked_get(self, connection: Any, record_type: str, record_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT payload FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND record_id = %s AND status = 'active'
             FOR UPDATE
            """,
            (self.context.workspace_id, _MODULE, record_type, record_id),
        ).fetchone()
        return dict(row[0]) if row is not None else None

    def _write(self, connection: Any, record_type: str, record_id: str, record: Any) -> None:
        connection.execute(
            """
            INSERT INTO omnix_module_records (
                workspace_id, module, record_type, record_id, owner_user_id,
                payload, status
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'active')
            ON CONFLICT (workspace_id, module, record_type, record_id)
            DO UPDATE SET payload = EXCLUDED.payload,
                          status = 'active',
                          revision = omnix_module_records.revision + 1,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (
                self.context.workspace_id,
                _MODULE,
                record_type,
                record_id,
                self.context.user_id,
                _json(record.model_dump(mode="json")),
            ),
        )


class PostgresCharacterVisemeGenerationRepositoryAdapter:
    """Persist generated viseme batches in the shared module-record authority."""
    context = RequestTenant()

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        self.context = None  # follows the request tenant

    def create(
        self,
        character_id: str,
        job_ids: dict[str, str],
    ) -> CharacterVisemeGenerationBatch:
        batch = CharacterVisemeGenerationBatch(
            id=f"avatar-visemes:{uuid.uuid4().hex}",
            character_id=character_id,
            status="generating",
            job_ids=dict(job_ids),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        with self.database.transaction() as connection:
            self._write(connection, batch.id, batch)
        return batch

    def get(self, batch_id: str) -> CharacterVisemeGenerationBatch | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND status = 'active'
                """,
                (self.context.workspace_id, _MODULE, _VISEME_BATCH_TYPE, batch_id),
            ).fetchone()
        return CharacterVisemeGenerationBatch.model_validate(dict(row[0])) if row is not None else None

    def list(self, character_id: str) -> list[CharacterVisemeGenerationBatch]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND status = 'active' AND payload->>'character_id' = %s
                 ORDER BY payload->>'created_at' DESC, record_id DESC
                 LIMIT 200
                """,
                (self.context.workspace_id, _MODULE, _VISEME_BATCH_TYPE, character_id),
            ).fetchall()
        return [CharacterVisemeGenerationBatch.model_validate(dict(row[0])) for row in rows]

    def update(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        job_ids: dict[str, str] | None = None,
        asset_ids: dict[str, str] | None = None,
        attempts: dict[str, int] | None = None,
        quality_fallbacks: dict[str, str] | None = None,
        avatar_pack_version: int | None = None,
        error: str | None = None,
    ) -> CharacterVisemeGenerationBatch:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND status = 'active'
                 FOR UPDATE
                """,
                (self.context.workspace_id, _MODULE, _VISEME_BATCH_TYPE, batch_id),
            ).fetchone()
            if row is None:
                raise KeyError(batch_id)
            current = dict(row[0])
            updated = CharacterVisemeGenerationBatch.model_validate(current).model_copy(
                update={
                    "status": status or current["status"],
                    "job_ids": dict(job_ids) if job_ids is not None else current.get("job_ids", {}),
                    "asset_ids": dict(asset_ids) if asset_ids is not None else current.get("asset_ids", {}),
                    "attempts": dict(attempts) if attempts is not None else current.get("attempts", {}),
                    "quality_fallbacks": (
                        dict(quality_fallbacks)
                        if quality_fallbacks is not None
                        else current.get("quality_fallbacks", {})
                    ),
                    "avatar_pack_version": (
                        avatar_pack_version
                        if avatar_pack_version is not None
                        else current.get("avatar_pack_version")
                    ),
                    "error": error if error is not None else current.get("error", ""),
                    "updated_at": _utcnow(),
                }
            )
            self._write(connection, batch_id, updated)
        return updated

    def _write(self, connection: Any, record_id: str, record: Any) -> None:
        connection.execute(
            """
            INSERT INTO omnix_module_records (
                workspace_id, module, record_type, record_id, owner_user_id,
                payload, status
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'active')
            ON CONFLICT (workspace_id, module, record_type, record_id)
            DO UPDATE SET payload = EXCLUDED.payload,
                          status = 'active',
                          revision = omnix_module_records.revision + 1,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (
                self.context.workspace_id,
                _MODULE,
                _VISEME_BATCH_TYPE,
                record_id,
                self.context.user_id,
                _json(record.model_dump(mode="json")),
            ),
        )


__all__ = [
    "PostgresCharacterAvatarGenerationRepositoryAdapter",
    "PostgresCharacterVisemeGenerationRepositoryAdapter",
]
