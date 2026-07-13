from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
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
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-outbox-direct-writer-tests",
        )
    )


def test_database_generates_unique_event_keys_for_atomic_direct_writers() -> None:
    database = _database()
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        with database.transaction() as connection:
            connection.execute(
                "DELETE FROM omnix_outbox_events WHERE aggregate_id = %s",
                ("compat:direct-writer",),
            )
            keys: list[str] = []
            for event_type in ("compat.first", "compat.second"):
                row = connection.execute(
                    """
                    INSERT INTO omnix_outbox_events (
                        workspace_id, aggregate_type, aggregate_id,
                        event_type, ordering_key, payload
                    ) VALUES (%s, 'compat', %s, %s, %s, '{}'::jsonb)
                    RETURNING event_key
                    """,
                    (
                        context.workspace_id,
                        "compat:direct-writer",
                        event_type,
                        "compat:direct-writer",
                    ),
                ).fetchone()
                keys.append(str(row[0]))

        assert len(set(keys)) == 2
        assert all(key.startswith("event:") for key in keys)
    finally:
        database.close()
