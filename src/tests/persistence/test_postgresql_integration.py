from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations, migration_status


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
            application_name="omnix-persistence-tests",
        )
    )


def test_postgresql_health_and_migration_idempotency() -> None:
    database = _database()
    try:
        health = database.health()
        assert health["ok"] is True
        assert health["backend"] == "postgresql"

        first = apply_migrations(database)
        second = apply_migrations(database)
        status = migration_status(database)

        assert first["ok"] is True
        assert "0001_platform" in first["applied"]
        assert second["applied_now"] == []
        assert status["pending"] == []
        assert status["checksum_drift"] == []
        assert status["unknown_applied"] == []
    finally:
        database.close()


def test_postgresql_transaction_rolls_back() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with pytest.raises(RuntimeError, match="rollback probe"):
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO omnix_database_events (event_type, payload) "
                    "VALUES (%s, %s::jsonb)",
                    ("test.rollback", "{}"),
                )
                raise RuntimeError("rollback probe")
        with database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM omnix_database_events WHERE event_type = %s",
                ("test.rollback",),
            ).fetchone()[0]
        assert count == 0
    finally:
        database.close()
