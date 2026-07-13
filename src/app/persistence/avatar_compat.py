from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.characters.avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from app.characters.repository import CharacterConflictError

from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready


_MODULE = "character-avatar"
_RECORD_TYPE = "avatar-pack"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PostgresCharacterAvatarRepositoryAdapter:
    """Tenant-scoped avatar-pack repository over bounded PostgreSQL documents."""

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def get(self, character_id: str) -> CharacterAvatarPack | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND status = 'active'
                """,
                (self.context.workspace_id, _MODULE, _RECORD_TYPE, character_id),
            ).fetchone()
        if row is None:
            return None
        return CharacterAvatarPack.model_validate(dict(row[0]))

    def upsert(
        self,
        character_id: str,
        request: UpsertCharacterAvatarPackRequest,
    ) -> CharacterAvatarPack:
        with self.database.transaction() as connection:
            current = self._locked_get(connection, character_id)
            current_version = current.version if current else 0
            if (
                request.expected_version is not None
                and request.expected_version != current_version
            ):
                raise CharacterConflictError(
                    "avatar pack version conflict: "
                    f"expected {request.expected_version}, current {current_version}"
                )
            now = _utcnow()
            pack = CharacterAvatarPack(
                character_id=character_id,
                version=current_version + 1,
                render_mode=request.render_mode,
                renderer=request.renderer,
                rig_asset_id=request.rig_asset_id,
                base_asset_id=request.base_asset_id,
                mouth_frames=dict(request.mouth_frames),
                blink_frames=dict(request.blink_frames),
                expression_frames=dict(request.expression_frames),
                outfit_frames=dict(request.outfit_frames),
                background_asset_ids=dict(request.background_asset_ids),
                active_outfit=request.active_outfit,
                active_background=request.active_background,
                mouth_anchor=dict(request.mouth_anchor),
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            self._write(connection, pack)
        return pack

    def import_pack(
        self,
        pack: CharacterAvatarPack,
        *,
        replace: bool = False,
    ) -> CharacterAvatarPack:
        """Import an exact verified pack, refusing non-identical replacement by default."""

        with self.database.transaction() as connection:
            current = self._locked_get(connection, pack.character_id)
            if current is not None:
                if current == pack:
                    return current
                if not replace:
                    raise CharacterConflictError(
                        f"avatar pack already exists: {pack.character_id}"
                    )
            self._write(connection, pack)
        return pack

    def delete(self, character_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s
                """,
                (self.context.workspace_id, _MODULE, _RECORD_TYPE, character_id),
            )
        return cursor.rowcount == 1

    def _locked_get(self, connection: Any, character_id: str) -> CharacterAvatarPack | None:
        row = connection.execute(
            """
            SELECT payload FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND record_id = %s AND status = 'active'
             FOR UPDATE
            """,
            (self.context.workspace_id, _MODULE, _RECORD_TYPE, character_id),
        ).fetchone()
        if row is None:
            return None
        return CharacterAvatarPack.model_validate(dict(row[0]))

    def _write(self, connection: Any, pack: CharacterAvatarPack) -> None:
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
                _RECORD_TYPE,
                pack.character_id,
                self.context.user_id,
                _json(pack.model_dump(mode="json")),
            ),
        )


__all__ = ["PostgresCharacterAvatarRepositoryAdapter"]
