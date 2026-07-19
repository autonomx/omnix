from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-owner-memory-authority-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_chat_messages, omnix_chat_sessions, "
            "omnix_memory_snapshot_items, omnix_memory_snapshots, "
            "omnix_memory_candidates, omnix_memory_events, omnix_memory_records, "
            "omnix_conversation_segments, omnix_character_versions, omnix_characters, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )
        connection.execute(
            """
            UPDATE omnix_persistence_cutover
               SET mode = 'postgresql', import_run_id = NULL,
                   source_hash = NULL, rollback_recorded_at = NULL,
                   metadata = '{}'::jsonb, updated_at = CURRENT_TIMESTAMP
             WHERE singleton = TRUE
            """
        )


_WRITE_SCRIPT = r"""
from app.persistence.startup import bootstrap_postgresql_runtime
bootstrap_postgresql_runtime()

from app.assistant_memory.models import MemoryScopeContext
from app.assistant_memory.owner_defaults import (
    default_memory_service,
    reset_default_memory_service,
)

system = MemoryScopeContext(
    profile_id="profile:default",
    workspace_id="workspace:local",
    project_id=None,
    session_id="chat:memory-authority",
    owner_type="system",
    owner_id="system-assistant",
)
maya = system.model_copy(
    update={"owner_type": "character", "owner_id": "character:maya"}
)

service = default_memory_service()
assert service.repository.__class__.__name__ == "PostgresOwnerAwareMemoryRepository"
system_record = service.create_explicit_memory(
    system,
    scope="workspace",
    category="fact",
    content="The commute uses Route X",
    provenance_id="message:system",
)
maya_record = service.create_explicit_memory(
    maya,
    scope="workspace",
    category="relationship",
    content="The commute uses Route X",
    provenance_id="message:maya",
)
candidate = service.propose_memory(
    maya,
    source_session_id=maya.session_id,
    source_message_id="message:candidate",
    scope="global",
    category="preference",
    content="Prefers a quiet morning greeting",
    confidence=0.9,
)
approved = service.approve_candidate(maya, candidate.id)
assert approved.owner_type == "character"
assert approved.owner_id == "character:maya"
assert approved.scope == "global"

snapshot = service.create_session_snapshot(system, token_budget=1000)
assert snapshot.owner_type == "system"
assert snapshot.owner_id == "system-assistant"
assert snapshot.session_id == system.session_id

reset_default_memory_service()
reconstructed = default_memory_service()
assert reconstructed is not service
assert reconstructed.repository.__class__.__name__ == "PostgresOwnerAwareMemoryRepository"
assert reconstructed.repository.get_record(system_record.id).scope == "workspace"
assert reconstructed.repository.get_record(maya_record.id).owner_id == "character:maya"
print("owner-memory-write-ok")
"""


_READ_SCRIPT = r"""
from app.persistence.startup import bootstrap_postgresql_runtime
bootstrap_postgresql_runtime()

from app.assistant_memory.models import MemoryScopeContext
from app.assistant_memory.owner_defaults import default_memory_service

system = MemoryScopeContext(
    profile_id="profile:default",
    workspace_id="workspace:local",
    project_id=None,
    session_id="chat:memory-authority",
    owner_type="system",
    owner_id="system-assistant",
)
maya = system.model_copy(
    update={"owner_type": "character", "owner_id": "character:maya"}
)
other = system.model_copy(
    update={"owner_type": "character", "owner_id": "character:other"}
)

service = default_memory_service()
system_records = service.list_active(system)
maya_records = service.list_active(maya)
other_records = service.list_active(other)

assert [item.content for item in system_records] == ["The commute uses Route X"]
assert {item.content for item in maya_records} == {
    "The commute uses Route X",
    "Prefers a quiet morning greeting",
}
assert other_records == []
assert all(item.owner_type == "system" for item in system_records)
assert all(item.owner_id == "character:maya" for item in maya_records)

snapshot = service.repository.latest_snapshot(
    system.session_id,
    owner_type=system.owner_type,
    owner_id=system.owner_id,
)
assert snapshot is not None
assert snapshot.session_id == system.session_id
assert snapshot.owner_type == "system"
print("owner-memory-read-ok")
"""


def _environment(tmp_path: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": "src",
            "OMNIX_DATABASE_URL": os.environ["OMNIX_TEST_DATABASE_URL"],
            "OMNIX_PERSISTENCE_MODE": "postgresql",
            "OMNIX_BLOB_ROOT": str(tmp_path / "blobs"),
        }
    )
    return environment


def _run(script: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_owner_memory_is_postgresql_authoritative_across_processes(
    tmp_path: Path,
) -> None:
    database = _database()
    try:
        _reset(database)
    finally:
        database.close()

    environment = _environment(tmp_path)
    written = _run(_WRITE_SCRIPT, environment)
    assert written.returncode == 0, (
        f"stdout:\n{written.stdout}\n\nstderr:\n{written.stderr}"
    )
    assert "owner-memory-write-ok" in written.stdout

    read = _run(_READ_SCRIPT, environment)
    assert read.returncode == 0, (
        f"stdout:\n{read.stdout}\n\nstderr:\n{read.stderr}"
    )
    assert "owner-memory-read-ok" in read.stdout
