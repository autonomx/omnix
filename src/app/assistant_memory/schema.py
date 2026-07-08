"""SQLite schema for backend-owned Chat and Character memory."""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL DEFAULT 'system',
    owner_id TEXT NOT NULL DEFAULT 'system-assistant',
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    normalized_content TEXT NOT NULL,
    confidence REAL NOT NULL,
    pinned INTEGER NOT NULL,
    trust_level TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    provenance_type TEXT NOT NULL,
    provenance_id TEXT,
    status TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_records_owner_scope ON memory_records(owner_type, owner_id, scope, scope_id, status, pinned, updated_at);
CREATE INDEX IF NOT EXISTS idx_memory_records_normalized ON memory_records(owner_type, owner_id, scope, scope_id, normalized_content);

CREATE TABLE IF NOT EXISTS memory_candidates (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL DEFAULT 'system',
    owner_id TEXT NOT NULL DEFAULT 'system-assistant',
    source_session_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    candidate_fingerprint TEXT NOT NULL,
    proposed_scope TEXT NOT NULL,
    proposed_scope_id TEXT NOT NULL,
    proposed_category TEXT NOT NULL,
    proposed_content TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    extraction_metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(owner_type, owner_id, source_message_id, candidate_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_memory_candidates_owner_status ON memory_candidates(owner_type, owner_id, status, created_at, id);

CREATE TABLE IF NOT EXISTS memory_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    owner_type TEXT NOT NULL DEFAULT 'system',
    owner_id TEXT NOT NULL DEFAULT 'system-assistant',
    revision INTEGER NOT NULL,
    token_estimate INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    refreshed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_snapshots_owner_revision ON memory_snapshots(session_id, owner_type, owner_id, revision);

CREATE TABLE IF NOT EXISTS memory_snapshot_items (
    snapshot_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    memory_record_id TEXT NOT NULL,
    record_revision INTEGER NOT NULL,
    frozen_content TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY(snapshot_id, memory_record_id),
    FOREIGN KEY(snapshot_id) REFERENCES memory_snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_snapshot_items_record ON memory_snapshot_items(memory_record_id, revoked_at);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_events_entity ON memory_events(entity_type, entity_id, id);
"""

_OWNER_COLUMNS = {
    "memory_records": {
        "owner_type": "TEXT NOT NULL DEFAULT 'system'",
        "owner_id": "TEXT NOT NULL DEFAULT 'system-assistant'",
    },
    "memory_candidates": {
        "owner_type": "TEXT NOT NULL DEFAULT 'system'",
        "owner_id": "TEXT NOT NULL DEFAULT 'system-assistant'",
    },
    "memory_snapshots": {
        "owner_type": "TEXT NOT NULL DEFAULT 'system'",
        "owner_id": "TEXT NOT NULL DEFAULT 'system-assistant'",
    },
}


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)
    row = connection.execute("SELECT version FROM memory_schema_version LIMIT 1").fetchone()
    if row is None:
        connection.execute("INSERT INTO memory_schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        return
    version = int(row[0])
    if version == 1:
        for table, columns in _OWNER_COLUMNS.items():
            existing = {item[1] for item in connection.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        connection.execute("DROP INDEX IF EXISTS idx_memory_records_scope")
        connection.execute("DROP INDEX IF EXISTS idx_memory_records_normalized")
        connection.execute("DROP INDEX IF EXISTS idx_memory_candidates_status")
        connection.execute("DROP INDEX IF EXISTS idx_memory_snapshots_session_revision")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_records_owner_scope ON memory_records(owner_type, owner_id, scope, scope_id, status, pinned, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_records_normalized ON memory_records(owner_type, owner_id, scope, scope_id, normalized_content)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_owner_status ON memory_candidates(owner_type, owner_id, status, created_at, id)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_snapshots_owner_revision ON memory_snapshots(session_id, owner_type, owner_id, revision)")
        connection.execute("UPDATE memory_schema_version SET version = ?", (SCHEMA_VERSION,))
        return
    if version != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported assistant memory schema version: {version} (expected {SCHEMA_VERSION})")
