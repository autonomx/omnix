"""Deleting a memory owner unpins chat sessions through the foreign key, in the same transaction (PA-3.2)."""
from __future__ import annotations

import os
import uuid

import pytest

from app.platform.assistant_memory.persistence.owner_memory_store import PostgresOwnerAwareMemoryRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def database():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    try:
        yield database
    finally:
        database.close()


def test_a_reset_owner_leaves_no_chat_session_pinned_to_its_snapshots(database) -> None:
    suffix = uuid.uuid4().hex[:8]
    owner, snapshot_id, session_id, other = f"character:{suffix}", f"snapshot:{suffix}", f"chat:{suffix}", f"chat:o{suffix}"
    workspace = current_tenant().workspace_id
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO omnix_memory_snapshots (id, workspace_id, owner_type, owner_id, revision) VALUES (%s, %s, 'character', %s, 1)",
            (snapshot_id, workspace, owner),
        )
        connection.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, memory_snapshot_id) VALUES (%s, %s, 'pinned', %s)",
            (session_id, workspace, snapshot_id),
        )
        connection.execute("INSERT INTO omnix_chat_sessions (id, workspace_id, title) VALUES (%s, %s, 'unpinned')",
                           (other, workspace))

    counts = PostgresOwnerAwareMemoryRepository(database).delete_owner(owner_type="character", owner_id=owner)

    with database.connection() as connection:
        pinned = dict(connection.execute(
            "SELECT id, memory_snapshot_id FROM omnix_chat_sessions WHERE id = ANY(%s)", ([session_id, other],),
        ).fetchall())
    assert counts[2] == 1
    assert pinned == {session_id: None, other: None}
