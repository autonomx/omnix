from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.assistant_memory.models import MemoryScopeContext
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.assistant_memory.typed_memory import create_typed_memory, supersede_typed_memory
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.owner_memory_compat import PostgresOwnerAwareMemoryRepository


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-typed-memory-tests",
        )
    )
    apply_migrations(database)
    return database


def test_typed_memory_round_trip_and_supersession() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        with database.transaction() as connection:
            connection.execute(
                "TRUNCATE omnix_memory_snapshot_items, omnix_memory_snapshots, "
                "omnix_memory_candidates, omnix_memory_events, omnix_memory_records CASCADE"
            )
        service = OwnerAwareMemoryService(PostgresOwnerAwareMemoryRepository(database))
        scope = MemoryScopeContext(
            profile_id="profile:default",
            workspace_id=context.workspace_id,
            project_id=None,
            session_id="chat:typed-postgres",
            owner_type="character",
            owner_id="character:maya",
        )
        original = create_typed_memory(
            service,
            scope,
            kind="routine",
            content="The user drives Route X around seven.",
            payload={
                "activity": "commute_to_work",
                "days": ["MO", "TU", "WE", "TH", "FR"],
                "start_time": "07:00",
                "timezone": "America/Vancouver",
                "evidence_count": 3,
            },
            provenance_id="message:typed",
        )
        loaded = service.repository.get_record(original.id)
        assert loaded is not None
        assert loaded.kind == "routine"
        assert loaded.owner_id == "character:maya"
        assert loaded.scope == "global"
        assert loaded.structured_payload["start_time"] == "07:00"

        replacement = supersede_typed_memory(
            service,
            scope,
            original.id,
            kind="routine",
            content="The user now takes the train.",
            payload={
                "activity": "commute_to_work",
                "days": ["MO", "TU", "WE", "TH", "FR"],
                "start_time": "07:00",
                "timezone": "America/Vancouver",
                "evidence_count": 1,
            },
            provenance_id=f"message:{datetime.now(timezone.utc).timestamp()}",
        )
        archived = service.repository.get_record(original.id)
        assert archived is not None and archived.status == "superseded"
        assert replacement.supersedes_memory_id == original.id
        assert replacement.contradiction_group == f"memory-claim:{original.id}"
    finally:
        database.close()
