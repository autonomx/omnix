"""The PostgreSQL memory adapter stores and reads session snapshots in today's schema."""
from __future__ import annotations

import os
import uuid

import pytest

from app.conversation.memory_contracts import MemorySnapshot, MemorySnapshotItem
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.platform.assistant_memory.persistence.memory_store import PostgresMemoryRepositoryAdapter
from app.runtime.tenant_context import pop_tenant, push_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def adapter():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    token = push_tenant(ensure_local_identity(database))
    try:
        yield PostgresMemoryRepositoryAdapter(database)
    finally:
        pop_tenant(token)
        database.close()


def test_a_session_snapshot_round_trips(adapter) -> None:
    session_id = f"chat:{uuid.uuid4().hex}"
    # Snapshots are unique per owner and revision: a character of its own.
    owner_id = f"character:{uuid.uuid4().hex[:12]}"
    snapshot = MemorySnapshot(
        id=f"snapshot:{uuid.uuid4().hex}",
        session_id=session_id,
        owner_type="character",
        owner_id=owner_id,
        revision=1,
        token_estimate=42,
        created_at="2026-10-06T12:00:00+00:00",
        items=[
            MemorySnapshotItem(memory_record_id="memory:a", record_revision=2, frozen_content="likes tea"),
            MemorySnapshotItem(memory_record_id="memory:b", record_revision=1, frozen_content="lives in Oslo"),
        ],
    )
    adapter.create_snapshot(snapshot)

    stored = adapter.get_snapshot(snapshot.id)
    assert stored is not None
    assert (stored.session_id, stored.owner_type, stored.owner_id, stored.token_estimate) == (
        session_id, "character", owner_id, 42)
    assert [(item.memory_record_id, item.frozen_content) for item in stored.items] == [
        ("memory:a", "likes tea"), ("memory:b", "lives in Oslo")]
    latest = adapter.latest_snapshot(session_id)
    assert latest is not None and latest.id == snapshot.id
    assert snapshot.id in {item.id for item in adapter.list_snapshots(scope="character", scope_id=owner_id)}

    adapter.set_snapshot_status(snapshot.id, "superseded")
    assert adapter.latest_snapshot(session_id) is None
