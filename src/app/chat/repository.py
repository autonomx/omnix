"""Repository abstraction and SQLite implementation for Chat history."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.runtime_paths import resources_data_root

from .models import ChatMessage, ChatSession
from .sqlite_schema import initialize_chat_schema


class ChatRepository(Protocol):
    def load_sessions(self) -> list[ChatSession]: ...

    def save_sessions(self, sessions: list[ChatSession]) -> None: ...


class ChatImportState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    source_hash: str
    status: str
    imported_session_count: int = Field(ge=0)
    imported_message_count: int = Field(ge=0)
    skipped_session_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    updated_at: str


def default_chat_db_path() -> Path:
    override = (os.environ.get("OMNIX_CHAT_SQLITE_DB_PATH") or "").strip()
    if override:
        return Path(override)
    return resources_data_root() / "omnix_chat.sqlite3"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SQLiteChatRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_chat_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            initialize_chat_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def load_sessions(self) -> list[ChatSession]:
        with self._connect() as connection:
            session_rows = connection.execute(
                "SELECT * FROM chat_sessions ORDER BY created_at ASC, id ASC"
            ).fetchall()
            message_rows = connection.execute(
                "SELECT * FROM chat_messages ORDER BY session_id ASC, position ASC"
            ).fetchall()
        grouped: dict[str, list[ChatMessage]] = {}
        for row in message_rows:
            grouped.setdefault(row["session_id"], []).append(
                ChatMessage(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                    metadata=json.loads(row["metadata_json"] or "{}"),
                )
            )
        return [self._row_to_session(row, grouped.get(row["id"], [])) for row in session_rows]

    def save_sessions(self, sessions: list[ChatSession]) -> None:
        with self._connect() as connection:
            self._delete_missing_sessions(connection, [session.id for session in sessions])
            self._upsert_sessions(connection, sessions)

    def import_sessions(
        self,
        *,
        source_path: str,
        source_hash: str,
        sessions: list[ChatSession],
        skipped_session_count: int,
        errors: list[str],
        updated_at: str,
    ) -> ChatImportState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_import_state WHERE source_path = ?",
                (source_path,),
            ).fetchone()
            if row and row["source_hash"] == source_hash and row["status"] == "completed":
                return self._row_to_import_state(row)
            self._upsert_sessions(connection, sessions)
            state = ChatImportState(
                source_path=source_path,
                source_hash=source_hash,
                status="completed",
                imported_session_count=len(sessions),
                imported_message_count=sum(len(session.messages) for session in sessions),
                skipped_session_count=skipped_session_count,
                errors=errors,
                updated_at=updated_at,
            )
            self._write_import_state(connection, state)
        return state

    def record_failed_import(
        self,
        *,
        source_path: str,
        source_hash: str,
        error: str,
        updated_at: str,
    ) -> ChatImportState:
        state = ChatImportState(
            source_path=source_path,
            source_hash=source_hash,
            status="failed",
            imported_session_count=0,
            imported_message_count=0,
            skipped_session_count=0,
            errors=[error],
            updated_at=updated_at,
        )
        with self._connect() as connection:
            self._write_import_state(connection, state)
        return state

    def get_import_state(self, source_path: str) -> ChatImportState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_import_state WHERE source_path = ?",
                (source_path,),
            ).fetchone()
        return self._row_to_import_state(row) if row else None

    def counts(self) -> tuple[int, int]:
        with self._connect() as connection:
            session_count = int(connection.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0])
            message_count = int(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])
        return session_count, message_count

    def _upsert_sessions(self, connection: sqlite3.Connection, sessions: list[ChatSession]) -> None:
        for session in sessions:
            connection.execute(
                """
                INSERT INTO chat_sessions (
                    id, title, provider_id, model_id, research_mode_override,
                    profile_id, workspace_id, project_id, memory_enabled,
                    memory_snapshot_id, memory_snapshot_revision, memory_record_count,
                    memory_last_refreshed_at, interaction_mode, character_id,
                    voice_asset_id, read_memory, write_memory, shared_memory_access,
                    transcript_policy, active_segment_id, character_profile_version,
                    effective_identity_hash, message_count, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    provider_id = excluded.provider_id,
                    model_id = excluded.model_id,
                    research_mode_override = excluded.research_mode_override,
                    profile_id = excluded.profile_id,
                    workspace_id = excluded.workspace_id,
                    project_id = excluded.project_id,
                    memory_enabled = excluded.memory_enabled,
                    memory_snapshot_id = excluded.memory_snapshot_id,
                    memory_snapshot_revision = excluded.memory_snapshot_revision,
                    memory_record_count = excluded.memory_record_count,
                    memory_last_refreshed_at = excluded.memory_last_refreshed_at,
                    interaction_mode = excluded.interaction_mode,
                    character_id = excluded.character_id,
                    voice_asset_id = excluded.voice_asset_id,
                    read_memory = excluded.read_memory,
                    write_memory = excluded.write_memory,
                    shared_memory_access = excluded.shared_memory_access,
                    transcript_policy = excluded.transcript_policy,
                    active_segment_id = excluded.active_segment_id,
                    character_profile_version = excluded.character_profile_version,
                    effective_identity_hash = excluded.effective_identity_hash,
                    message_count = excluded.message_count,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.id,
                    session.title,
                    session.provider_id,
                    session.model_id,
                    session.research_mode_override,
                    session.profile_id,
                    session.workspace_id,
                    session.project_id,
                    int(session.memory_enabled),
                    session.memory_snapshot_id,
                    session.memory_snapshot_revision,
                    session.memory_record_count,
                    session.memory_last_refreshed_at,
                    session.interaction_mode,
                    session.character_id,
                    session.voice_asset_id,
                    int(session.read_memory),
                    int(session.write_memory),
                    session.shared_memory_access,
                    session.transcript_policy,
                    session.active_segment_id,
                    session.character_profile_version,
                    session.effective_identity_hash,
                    len(session.messages),
                    session.created_at,
                    session.updated_at,
                ),
            )
            connection.execute("DELETE FROM chat_messages WHERE session_id = ?", (session.id,))
            for position, message in enumerate(session.messages):
                connection.execute(
                    """
                    INSERT INTO chat_messages(
                        id, session_id, position, role, content, created_at, metadata_json
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        message.id,
                        session.id,
                        position,
                        message.role,
                        message.content,
                        message.created_at,
                        _json_dumps(message.metadata),
                    ),
                )

    @staticmethod
    def _delete_missing_sessions(connection: sqlite3.Connection, session_ids: list[str]) -> None:
        if not session_ids:
            connection.execute("DELETE FROM chat_sessions")
            return
        placeholders = ",".join("?" for _ in session_ids)
        connection.execute(
            f"DELETE FROM chat_sessions WHERE id NOT IN ({placeholders})",  # noqa: S608
            tuple(session_ids),
        )

    @staticmethod
    def _row_to_session(row: sqlite3.Row, messages: list[ChatMessage]) -> ChatSession:
        return ChatSession(
            id=row["id"],
            title=row["title"],
            provider_id=row["provider_id"],
            model_id=row["model_id"],
            research_mode_override=row["research_mode_override"],
            profile_id=row["profile_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
            memory_enabled=bool(row["memory_enabled"]),
            memory_snapshot_id=row["memory_snapshot_id"],
            memory_snapshot_revision=row["memory_snapshot_revision"],
            memory_record_count=int(row["memory_record_count"]),
            memory_last_refreshed_at=row["memory_last_refreshed_at"],
            interaction_mode=row["interaction_mode"],
            character_id=row["character_id"],
            voice_asset_id=row["voice_asset_id"],
            read_memory=bool(row["read_memory"]),
            write_memory=bool(row["write_memory"]),
            shared_memory_access=row["shared_memory_access"],
            transcript_policy=row["transcript_policy"],
            active_segment_id=row["active_segment_id"],
            character_profile_version=row["character_profile_version"],
            effective_identity_hash=row["effective_identity_hash"],
            message_count=len(messages),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=messages,
        )

    @staticmethod
    def _write_import_state(connection: sqlite3.Connection, state: ChatImportState) -> None:
        connection.execute(
            """
            INSERT INTO chat_import_state(
                source_path, source_hash, status, imported_session_count,
                imported_message_count, skipped_session_count, errors_json, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(source_path) DO UPDATE SET
                source_hash = excluded.source_hash,
                status = excluded.status,
                imported_session_count = excluded.imported_session_count,
                imported_message_count = excluded.imported_message_count,
                skipped_session_count = excluded.skipped_session_count,
                errors_json = excluded.errors_json,
                updated_at = excluded.updated_at
            """,
            (
                state.source_path,
                state.source_hash,
                state.status,
                state.imported_session_count,
                state.imported_message_count,
                state.skipped_session_count,
                _json_dumps(state.errors),
                state.updated_at,
            ),
        )

    @staticmethod
    def _row_to_import_state(row: sqlite3.Row) -> ChatImportState:
        return ChatImportState(
            source_path=row["source_path"],
            source_hash=row["source_hash"],
            status=row["status"],
            imported_session_count=int(row["imported_session_count"]),
            imported_message_count=int(row["imported_message_count"]),
            skipped_session_count=int(row["skipped_session_count"]),
            errors=json.loads(row["errors_json"] or "[]"),
            updated_at=row["updated_at"],
        )
