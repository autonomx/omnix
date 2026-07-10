"""SQLite persistence for versioned live-chat character avatar packs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from .repository import CharacterConflictError, default_character_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_avatar_packs (
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
);
"""


class CharacterAvatarRepository:
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

    def get(self, character_id: str) -> CharacterAvatarPack | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM character_avatar_packs WHERE character_id = ?",
                (character_id,),
            ).fetchone()
        return _row_to_pack(row) if row else None

    def upsert(
        self,
        character_id: str,
        request: UpsertCharacterAvatarPackRequest,
    ) -> CharacterAvatarPack:
        now = _utcnow()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM character_avatar_packs WHERE character_id = ?",
                (character_id,),
            ).fetchone()
            current = _row_to_pack(row) if row else None
            if request.expected_version is not None:
                current_version = current.version if current else 0
                if request.expected_version != current_version:
                    raise CharacterConflictError(
                        f"avatar pack version conflict: expected {request.expected_version}, current {current_version}"
                    )
            pack = CharacterAvatarPack(
                character_id=character_id,
                version=(current.version + 1) if current else 1,
                render_mode=request.render_mode,
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
            connection.execute(
                """
                INSERT INTO character_avatar_packs(
                    character_id, version, render_mode, base_asset_id,
                    mouth_frames_json, blink_frames_json, expression_frames_json,
                    outfit_frames_json, background_asset_ids_json, active_outfit,
                    active_background, mouth_anchor_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(character_id) DO UPDATE SET
                    version=excluded.version,
                    render_mode=excluded.render_mode,
                    base_asset_id=excluded.base_asset_id,
                    mouth_frames_json=excluded.mouth_frames_json,
                    blink_frames_json=excluded.blink_frames_json,
                    expression_frames_json=excluded.expression_frames_json,
                    outfit_frames_json=excluded.outfit_frames_json,
                    background_asset_ids_json=excluded.background_asset_ids_json,
                    active_outfit=excluded.active_outfit,
                    active_background=excluded.active_background,
                    mouth_anchor_json=excluded.mouth_anchor_json,
                    updated_at=excluded.updated_at
                """,
                _pack_values(pack),
            )
        return pack

    def delete(self, character_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM character_avatar_packs WHERE character_id = ?",
                (character_id,),
            )
        return cursor.rowcount > 0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _pack_values(pack: CharacterAvatarPack) -> tuple[Any, ...]:
    return (
        pack.character_id,
        pack.version,
        pack.render_mode,
        pack.base_asset_id,
        _json(pack.mouth_frames),
        _json(pack.blink_frames),
        _json(pack.expression_frames),
        _json(pack.outfit_frames),
        _json(pack.background_asset_ids),
        pack.active_outfit,
        pack.active_background,
        _json(pack.mouth_anchor),
        pack.created_at,
        pack.updated_at,
    )


def _row_to_pack(row: sqlite3.Row) -> CharacterAvatarPack:
    return CharacterAvatarPack(
        character_id=row["character_id"],
        version=int(row["version"]),
        render_mode=row["render_mode"],
        base_asset_id=row["base_asset_id"],
        mouth_frames=json.loads(row["mouth_frames_json"] or "{}"),
        blink_frames=json.loads(row["blink_frames_json"] or "{}"),
        expression_frames=json.loads(row["expression_frames_json"] or "{}"),
        outfit_frames=json.loads(row["outfit_frames_json"] or "{}"),
        background_asset_ids=json.loads(row["background_asset_ids_json"] or "{}"),
        active_outfit=row["active_outfit"],
        active_background=row["active_background"],
        mouth_anchor=json.loads(row["mouth_anchor_json"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = ["CharacterAvatarRepository"]
