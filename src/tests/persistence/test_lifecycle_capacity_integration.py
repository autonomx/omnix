from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.lifecycle import PostgresLifecycleRepository
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
            application_name="omnix-lifecycle-capacity-tests",
        )
    )


def test_cleanup_removes_only_expired_terminal_records() -> None:
    database = _database()
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        with database.transaction() as connection:
            connection.execute(
                "DELETE FROM omnix_outbox_consumer_inbox; "
                "DELETE FROM omnix_outbox_dead_letters; "
                "DELETE FROM omnix_outbox_events; "
                "DELETE FROM omnix_runtime_failure_evidence; "
                "DELETE FROM omnix_lifecycle_cleanup_runs"
            )
            old_id = connection.execute(
                """
                INSERT INTO omnix_outbox_events (
                    event_key, workspace_id, aggregate_type, aggregate_id,
                    event_type, payload, status, published_at, created_at
                ) VALUES (
                    'event:lifecycle-old', %s, 'test', 'old', 'test.old', '{}'::jsonb,
                    'published', CURRENT_TIMESTAMP - INTERVAL '40 days',
                    CURRENT_TIMESTAMP - INTERVAL '40 days'
                ) RETURNING id
                """,
                (context.workspace_id,),
            ).fetchone()[0]
            recent_id = connection.execute(
                """
                INSERT INTO omnix_outbox_events (
                    event_key, workspace_id, aggregate_type, aggregate_id,
                    event_type, payload, status, published_at
                ) VALUES (
                    'event:lifecycle-recent', %s, 'test', 'recent', 'test.recent',
                    '{}'::jsonb, 'published', CURRENT_TIMESTAMP
                ) RETURNING id
                """,
                (context.workspace_id,),
            ).fetchone()[0]
            pending_id = connection.execute(
                """
                INSERT INTO omnix_outbox_events (
                    event_key, workspace_id, aggregate_type, aggregate_id,
                    event_type, payload, status, created_at
                ) VALUES (
                    'event:lifecycle-pending', %s, 'test', 'pending', 'test.pending',
                    '{}'::jsonb, 'pending', CURRENT_TIMESTAMP - INTERVAL '100 days'
                ) RETURNING id
                """,
                (context.workspace_id,),
            ).fetchone()[0]
            lifecycle = PostgresLifecycleRepository(connection)
            result = lifecycle.cleanup(batch_size=100)
            assert result["ok"] is True
            assert result["deleted"]["outbox_events"] == 1
            remaining = {
                int(row[0])
                for row in connection.execute(
                    "SELECT id FROM omnix_outbox_events WHERE id IN (%s, %s, %s)",
                    (old_id, recent_id, pending_id),
                ).fetchall()
            }
            assert old_id not in remaining
            assert recent_id in remaining
            assert pending_id in remaining
    finally:
        database.close()


def test_capacity_report_exposes_bounded_policy() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.connection() as connection:
            report = PostgresLifecycleRepository(connection).capacity_report()
        assert report["database_bytes"] > 0
        assert report["policy"]["max_outbox_payload_bytes"] == 1_048_576
        assert report["policy"]["disk_warning_percent"] < report["policy"]["disk_hard_stop_percent"]
        assert set(report["counts"]) >= {"outbox_events", "rpg_turns", "audit_events"}
    finally:
        database.close()


def test_outbox_payload_capacity_is_database_enforced() -> None:
    database = _database()
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        with pytest.raises(Exception):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO omnix_outbox_events (
                        event_key, workspace_id, aggregate_type, aggregate_id,
                        event_type, payload
                    ) VALUES (
                        'event:oversized', %s, 'test', 'oversized', 'test.oversized',
                        jsonb_build_object('data', repeat('x', 1100000))
                    )
                    """,
                    (context.workspace_id,),
                )
    finally:
        database.close()
