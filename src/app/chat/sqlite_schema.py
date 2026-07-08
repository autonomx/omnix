"""SQLite schema for durable Chat sessions and messages."""
from __future__ import annotations

import sqlite3

CHAT_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    provider_id TEXT,
    model_id TEXT,
    research_mode_override TEXT,
    profile_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT,
    memory_enabled INTEGER NOT NULL,
    memory_snapshot_id TEXT,
    memory_snapshot_revision INTEGER,
    memory_record_count INTEGER NOT NULL,
    memory_last_refreshed_at TEXT,
    message_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
ON chat_sessions(updated_at DESC, id ASC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, position)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
ON chat_messages(session_id, position);

CREATE TABLE IF NOT EXISTS chat_session_metadata (
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    PRIMARY KEY(session_id, key),
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_import_state (
    source_path TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    imported_session_count INTEGER NOT NULL,
    imported_message_count INTEGER NOT NULL,
    skipped_session_count INTEGER NOT NULL,
    errors_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def initialize_chat_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)
    row = connection.execute("SELECT version FROM chat_schema_version LIMIT 1").fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO chat_schema_version(version) VALUES (?)",
            (CHAT_SCHEMA_VERSION,),
        )
        return
    if int(row[0]) != CHAT_SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported Chat schema version: {row[0]} (expected {CHAT_SCHEMA_VERSION})"
        )
