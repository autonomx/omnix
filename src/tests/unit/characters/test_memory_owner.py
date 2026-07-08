from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.assistant_memory import MemoryPolicyError, resolve_chat_scope, resolve_snapshot_view
from app.assistant_memory.owner_repository import OwnerAwareSQLiteMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService


def _service(tmp_path: Path) -> OwnerAwareMemoryService:
    return OwnerAwareMemoryService(
        OwnerAwareSQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    )


def _contexts():
    shared = {
        "session_id": "chat:shared",
        "profile_id": "profile:local",
        "workspace_id": "workspace:default",
    }
    return (
        resolve_chat_scope(**shared),
        resolve_chat_scope(**shared, owner_type="character", owner_id="maya"),
        resolve_chat_scope(**shared, owner_type="character", owner_id="alex"),
    )


def test_owner_filter_precedes_scope_selection(tmp_path: Path) -> None:
    service = _service(tmp_path)
    system, maya, alex = _contexts()
    service.create_explicit_memory(
        system,
        scope="global",
        category="preference",
        content="The user prefers concise system answers.",
        provenance_id="system-message",
    )
    service.create_explicit_memory(
        maya,
        scope="global",
        category="relationship",
        content="Maya and the user joke about rainy hikes.",
        provenance_id="maya-message",
    )
    service.create_explicit_memory(
        alex,
        scope="global",
        category="relationship",
        content="Alex and the user discuss music production.",
        provenance_id="alex-message",
    )

    assert [item.content for item in service.list_active(system)] == [
        "The user prefers concise system answers."
    ]
    assert [item.content for item in service.list_active(maya)] == [
        "Maya and the user joke about rainy hikes."
    ]
    assert [item.content for item in service.list_active(alex)] == [
        "Alex and the user discuss music production."
    ]


def test_cross_owner_mutations_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    system, maya, _ = _contexts()
    record = service.create_explicit_memory(
        maya,
        scope="session",
        category="relationship",
        content="A private Maya memory.",
        provenance_id="maya-message",
    )

    with pytest.raises(MemoryPolicyError, match="owner_mismatch"):
        service.edit_memory(
            system,
            record.id,
            content="System Assistant should not edit this.",
            expected_revision=record.revision,
        )
    with pytest.raises(MemoryPolicyError, match="owner_mismatch"):
        service.forget_memory(
            system,
            record.id,
            expected_revision=record.revision,
        )


def test_candidate_identity_and_approval_are_owner_isolated(tmp_path: Path) -> None:
    service = _service(tmp_path)
    system, maya, _ = _contexts()
    system_candidate = service.propose_memory(
        system,
        source_session_id="chat:shared",
        source_message_id="message:same",
        scope="global",
        category="preference",
        content="The user likes quiet cafés.",
        confidence=0.9,
    )
    maya_candidate = service.propose_memory(
        maya,
        source_session_id="chat:shared",
        source_message_id="message:same",
        scope="global",
        category="preference",
        content="The user likes quiet cafés.",
        confidence=0.9,
    )

    assert system_candidate.id != maya_candidate.id
    assert system_candidate.candidate_fingerprint != maya_candidate.candidate_fingerprint
    with pytest.raises(MemoryPolicyError, match="owner_mismatch"):
        service.approve_candidate(system, maya_candidate.id)
    approved = service.approve_candidate(maya, maya_candidate.id)
    assert approved.owner_type == "character"
    assert approved.owner_id == "maya"


def test_snapshots_have_independent_owner_revisions_and_visibility(tmp_path: Path) -> None:
    service = _service(tmp_path)
    system, maya, _ = _contexts()
    service.create_explicit_memory(
        system,
        scope="session",
        category="fact",
        content="System-owned fact.",
        provenance_id="system-message",
    )
    service.create_explicit_memory(
        maya,
        scope="session",
        category="relationship",
        content="Maya-owned relationship memory.",
        provenance_id="maya-message",
    )

    system_snapshot = service.create_session_snapshot(system, token_budget=1000)
    maya_snapshot = service.create_session_snapshot(maya, token_budget=1000)

    assert system_snapshot.revision == 1
    assert maya_snapshot.revision == 1
    assert system_snapshot.owner_id == "system-assistant"
    assert maya_snapshot.owner_id == "maya"
    assert resolve_snapshot_view(service, system, maya_snapshot.id) is None
    maya_view = resolve_snapshot_view(service, maya, maya_snapshot.id)
    assert maya_view is not None
    assert maya_view.active_count == 1


def test_v1_database_migrates_existing_rows_to_system_owner(tmp_path: Path) -> None:
    path = tmp_path / "legacy-memory.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE memory_schema_version(version INTEGER NOT NULL);
            INSERT INTO memory_schema_version(version) VALUES (1);
            CREATE TABLE memory_records(
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
                category TEXT NOT NULL, source TEXT NOT NULL, content TEXT NOT NULL,
                normalized_content TEXT NOT NULL, confidence REAL NOT NULL,
                pinned INTEGER NOT NULL, trust_level TEXT NOT NULL,
                sensitivity TEXT NOT NULL, provenance_type TEXT NOT NULL,
                provenance_id TEXT, status TEXT NOT NULL, revision INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT
            );
            CREATE TABLE memory_candidates(
                id TEXT PRIMARY KEY, source_session_id TEXT NOT NULL,
                source_message_id TEXT NOT NULL, candidate_fingerprint TEXT NOT NULL,
                proposed_scope TEXT NOT NULL, proposed_scope_id TEXT NOT NULL,
                proposed_category TEXT NOT NULL, proposed_content TEXT NOT NULL,
                confidence REAL NOT NULL, source TEXT NOT NULL, trust_level TEXT NOT NULL,
                sensitivity TEXT NOT NULL, extraction_metadata_json TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT,
                UNIQUE(source_message_id, candidate_fingerprint)
            );
            CREATE TABLE memory_snapshots(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, revision INTEGER NOT NULL,
                token_estimate INTEGER NOT NULL, created_at TEXT NOT NULL, refreshed_at TEXT
            );
            CREATE UNIQUE INDEX idx_memory_snapshots_session_revision
            ON memory_snapshots(session_id, revision);
            CREATE TABLE memory_snapshot_items(
                snapshot_id TEXT NOT NULL, position INTEGER NOT NULL,
                memory_record_id TEXT NOT NULL, record_revision INTEGER NOT NULL,
                frozen_content TEXT NOT NULL, revoked_at TEXT,
                PRIMARY KEY(snapshot_id, memory_record_id)
            );
            CREATE TABLE memory_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, event_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            INSERT INTO memory_records VALUES(
                'memory:legacy','global','profile:local','fact','user_saved',
                'Legacy fact','legacy fact',1.0,0,'user_approved','normal',
                'user_message','message:legacy','active',1,
                '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',NULL
            );
            """
        )

    repository = OwnerAwareSQLiteMemoryRepository(path)
    records = repository.list_records()
    with sqlite3.connect(path) as connection:
        version = connection.execute("SELECT version FROM memory_schema_version").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(memory_records)")}

    assert version == 2
    assert {"owner_type", "owner_id"} <= columns
    assert records[0].owner_type == "system"
    assert records[0].owner_id == "system-assistant"
