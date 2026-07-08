"""Transactional SQLite persistence for characters, versions, and segments."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import resources_data_root

from .models import (
    CharacterProfile,
    CharacterProfileVersion,
    ConversationSegment,
    CreateCharacterRequest,
    InteractionMode,
    SharedMemoryAccess,
    TranscriptPolicy,
    UpdateCharacterRequest,
)

CHARACTER_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS character_schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS character_profiles (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    personality_prompt TEXT NOT NULL,
    default_greeting TEXT NOT NULL,
    default_voice_asset_id TEXT,
    speech_style_json TEXT NOT NULL,
    identity_policy_json TEXT NOT NULL,
    shared_memory_policy_json TEXT NOT NULL,
    active_version INTEGER NOT NULL,
    enabled INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_character_profiles_status_name
ON character_profiles(status, display_name COLLATE NOCASE, id);

CREATE TABLE IF NOT EXISTS character_profile_versions (
    character_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    personality_prompt TEXT NOT NULL,
    default_greeting TEXT NOT NULL,
    default_voice_asset_id TEXT,
    speech_style_json TEXT NOT NULL,
    identity_policy_json TEXT NOT NULL,
    shared_memory_policy_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(character_id, version),
    FOREIGN KEY(character_id) REFERENCES character_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS character_conversation_segments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    interaction_mode TEXT NOT NULL,
    character_id TEXT,
    profile_version INTEGER,
    transcript_policy TEXT NOT NULL,
    read_memory INTEGER NOT NULL,
    write_memory INTEGER NOT NULL,
    shared_memory_access TEXT NOT NULL,
    carryover_summary TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY(character_id) REFERENCES character_profiles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_character_segments_session_started
ON character_conversation_segments(session_id, started_at, id);
"""


class CharacterNotFoundError(KeyError):
    pass


class CharacterConflictError(RuntimeError):
    pass


class CharacterRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_character_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.executescript(_SCHEMA)
        row = connection.execute("SELECT version FROM character_schema_version LIMIT 1").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO character_schema_version(version) VALUES (?)",
                (CHARACTER_SCHEMA_VERSION,),
            )
        elif int(row[0]) != CHARACTER_SCHEMA_VERSION:
            raise RuntimeError(
                f"unsupported Character schema version: {row[0]} "
                f"(expected {CHARACTER_SCHEMA_VERSION})"
            )

    def create(self, request: CreateCharacterRequest) -> CharacterProfile:
        now = _utcnow()
        character_id = _normalize_character_id(request.id or request.display_name)
        profile = CharacterProfile(
            id=character_id,
            display_name=request.display_name.strip(),
            description=request.description.strip(),
            personality_prompt=request.personality_prompt.strip(),
            default_greeting=request.default_greeting.strip(),
            default_voice_asset_id=request.default_voice_asset_id,
            speech_style=dict(request.speech_style),
            identity_policy=dict(request.identity_policy),
            shared_memory_policy=dict(request.shared_memory_policy),
            active_version=1,
            enabled=request.enabled,
            status="active",
            created_at=now,
            updated_at=now,
        )
        version = _profile_version(profile)
        try:
            with self._connect() as connection:
                self._insert_profile(connection, profile)
                self._insert_version(connection, version)
        except sqlite3.IntegrityError as exc:
            raise CharacterConflictError(f"character already exists: {character_id}") from exc
        return profile

    def get(self, character_id: str, *, include_archived: bool = False) -> CharacterProfile | None:
        query = "SELECT * FROM character_profiles WHERE id = ?"
        params: tuple[Any, ...] = (character_id,)
        if not include_archived:
            query += " AND status = 'active'"
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return _row_to_profile(row) if row else None

    def list(self, *, include_archived: bool = False) -> list[CharacterProfile]:
        query = "SELECT * FROM character_profiles"
        if not include_archived:
            query += " WHERE status = 'active'"
        query += " ORDER BY display_name COLLATE NOCASE ASC, id ASC"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [_row_to_profile(row) for row in rows]

    def update(self, character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM character_profiles WHERE id = ? AND status = 'active'",
                (character_id,),
            ).fetchone()
            if row is None:
                raise CharacterNotFoundError(character_id)
            current = _row_to_profile(row)
            if current.active_version != request.expected_version:
                raise CharacterConflictError(
                    f"character version conflict: expected {request.expected_version}, "
                    f"current {current.active_version}"
                )
            changes = request.model_dump(exclude={"expected_version"}, exclude_none=True)
            if changes.pop("clear_default_voice", False):
                changes["default_voice_asset_id"] = None
            if not changes:
                return current
            payload = current.model_dump(mode="python")
            payload.update(changes)
            payload["active_version"] = current.active_version + 1
            payload["updated_at"] = _utcnow()
            updated = CharacterProfile(**payload)
            self._write_profile(connection, updated)
            self._insert_version(connection, _profile_version(updated))
        return updated

    def archive(self, character_id: str) -> CharacterProfile:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM character_profiles WHERE id = ?",
                (character_id,),
            ).fetchone()
            if row is None:
                raise CharacterNotFoundError(character_id)
            current = _row_to_profile(row)
            archived = current.model_copy(
                update={
                    "status": "archived",
                    "enabled": False,
                    "updated_at": _utcnow(),
                }
            )
            self._write_profile(connection, archived)
        return archived

    def versions(self, character_id: str) -> list[CharacterProfileVersion]:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM character_profiles WHERE id = ?",
                (character_id,),
            ).fetchone()
            if exists is None:
                raise CharacterNotFoundError(character_id)
            rows = connection.execute(
                """
                SELECT * FROM character_profile_versions
                WHERE character_id = ? ORDER BY version DESC
                """,
                (character_id,),
            ).fetchall()
        return [_row_to_version(row) for row in rows]

    def create_segment(
        self,
        *,
        session_id: str,
        interaction_mode: InteractionMode,
        character_id: str | None,
        profile_version: int | None,
        transcript_policy: TranscriptPolicy,
        read_memory: bool,
        write_memory: bool,
        shared_memory_access: SharedMemoryAccess,
        carryover_summary: str | None = None,
    ) -> ConversationSegment:
        if interaction_mode == "character" and not character_id:
            raise ValueError("character segment requires character_id")
        if interaction_mode == "system" and character_id:
            raise ValueError("system segment cannot have character_id")
        segment = ConversationSegment(
            id=f"segment:{uuid.uuid4().hex}",
            session_id=session_id,
            interaction_mode=interaction_mode,
            character_id=character_id,
            profile_version=profile_version,
            transcript_policy=transcript_policy,
            read_memory=read_memory,
            write_memory=write_memory,
            shared_memory_access=shared_memory_access,
            carryover_summary=carryover_summary,
            started_at=_utcnow(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO character_conversation_segments(
                    id, session_id, interaction_mode, character_id, profile_version,
                    transcript_policy, read_memory, write_memory, shared_memory_access,
                    carryover_summary, started_at, ended_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    segment.id,
                    segment.session_id,
                    segment.interaction_mode,
                    segment.character_id,
                    segment.profile_version,
                    segment.transcript_policy,
                    int(segment.read_memory),
                    int(segment.write_memory),
                    segment.shared_memory_access,
                    segment.carryover_summary,
                    segment.started_at,
                    segment.ended_at,
                ),
            )
        return segment

    def close_segment(self, segment_id: str) -> ConversationSegment | None:
        ended_at = _utcnow()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE character_conversation_segments
                SET ended_at = COALESCE(ended_at, ?)
                WHERE id = ?
                """,
                (ended_at, segment_id),
            )
            row = connection.execute(
                "SELECT * FROM character_conversation_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
        return _row_to_segment(row) if row else None

    def segments(self, session_id: str) -> list[ConversationSegment]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM character_conversation_segments
                WHERE session_id = ? ORDER BY started_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        return [_row_to_segment(row) for row in rows]

    @staticmethod
    def _insert_profile(connection: sqlite3.Connection, profile: CharacterProfile) -> None:
        connection.execute(
            """
            INSERT INTO character_profiles(
                id, display_name, description, personality_prompt, default_greeting,
                default_voice_asset_id, speech_style_json, identity_policy_json,
                shared_memory_policy_json, active_version, enabled, status,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            _profile_values(profile),
        )

    @staticmethod
    def _write_profile(connection: sqlite3.Connection, profile: CharacterProfile) -> None:
        connection.execute(
            """
            UPDATE character_profiles SET
                display_name = ?, description = ?, personality_prompt = ?,
                default_greeting = ?, default_voice_asset_id = ?, speech_style_json = ?,
                identity_policy_json = ?, shared_memory_policy_json = ?,
                active_version = ?, enabled = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                profile.display_name,
                profile.description,
                profile.personality_prompt,
                profile.default_greeting,
                profile.default_voice_asset_id,
                _json(profile.speech_style),
                _json(profile.identity_policy),
                _json(profile.shared_memory_policy),
                profile.active_version,
                int(profile.enabled),
                profile.status,
                profile.updated_at,
                profile.id,
            ),
        )

    @staticmethod
    def _insert_version(connection: sqlite3.Connection, version: CharacterProfileVersion) -> None:
        connection.execute(
            """
            INSERT INTO character_profile_versions(
                character_id, version, display_name, description, personality_prompt,
                default_greeting, default_voice_asset_id, speech_style_json,
                identity_policy_json, shared_memory_policy_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                version.character_id,
                version.version,
                version.display_name,
                version.description,
                version.personality_prompt,
                version.default_greeting,
                version.default_voice_asset_id,
                _json(version.speech_style),
                _json(version.identity_policy),
                _json(version.shared_memory_policy),
                version.created_at,
            ),
        )


def default_character_db_path() -> Path:
    override = (os.environ.get("OMNIX_CHARACTER_DB_PATH") or "").strip()
    return Path(override) if override else resources_data_root() / "omnix_characters.sqlite3"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_character_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        normalized = f"character-{uuid.uuid4().hex[:12]}"
    if len(normalized) > 160:
        normalized = normalized[:160].rstrip("-")
    return normalized


def _profile_values(profile: CharacterProfile) -> tuple[Any, ...]:
    return (
        profile.id,
        profile.display_name,
        profile.description,
        profile.personality_prompt,
        profile.default_greeting,
        profile.default_voice_asset_id,
        _json(profile.speech_style),
        _json(profile.identity_policy),
        _json(profile.shared_memory_policy),
        profile.active_version,
        int(profile.enabled),
        profile.status,
        profile.created_at,
        profile.updated_at,
    )


def _profile_version(profile: CharacterProfile) -> CharacterProfileVersion:
    return CharacterProfileVersion(
        character_id=profile.id,
        version=profile.active_version,
        display_name=profile.display_name,
        description=profile.description,
        personality_prompt=profile.personality_prompt,
        default_greeting=profile.default_greeting,
        default_voice_asset_id=profile.default_voice_asset_id,
        speech_style=dict(profile.speech_style),
        identity_policy=dict(profile.identity_policy),
        shared_memory_policy=dict(profile.shared_memory_policy),
        created_at=profile.updated_at,
    )


def _row_to_profile(row: sqlite3.Row) -> CharacterProfile:
    return CharacterProfile(
        id=row["id"],
        display_name=row["display_name"],
        description=row["description"],
        personality_prompt=row["personality_prompt"],
        default_greeting=row["default_greeting"],
        default_voice_asset_id=row["default_voice_asset_id"],
        speech_style=json.loads(row["speech_style_json"] or "{}"),
        identity_policy=json.loads(row["identity_policy_json"] or "{}"),
        shared_memory_policy=json.loads(row["shared_memory_policy_json"] or "{}"),
        active_version=int(row["active_version"]),
        enabled=bool(row["enabled"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_version(row: sqlite3.Row) -> CharacterProfileVersion:
    return CharacterProfileVersion(
        character_id=row["character_id"],
        version=int(row["version"]),
        display_name=row["display_name"],
        description=row["description"],
        personality_prompt=row["personality_prompt"],
        default_greeting=row["default_greeting"],
        default_voice_asset_id=row["default_voice_asset_id"],
        speech_style=json.loads(row["speech_style_json"] or "{}"),
        identity_policy=json.loads(row["identity_policy_json"] or "{}"),
        shared_memory_policy=json.loads(row["shared_memory_policy_json"] or "{}"),
        created_at=row["created_at"],
    )


def _row_to_segment(row: sqlite3.Row) -> ConversationSegment:
    return ConversationSegment(
        id=row["id"],
        session_id=row["session_id"],
        interaction_mode=row["interaction_mode"],
        character_id=row["character_id"],
        profile_version=row["profile_version"],
        transcript_policy=row["transcript_policy"],
        read_memory=bool(row["read_memory"]),
        write_memory=bool(row["write_memory"]),
        shared_memory_access=row["shared_memory_access"],
        carryover_summary=row["carryover_summary"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )
