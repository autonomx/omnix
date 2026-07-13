from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import (
    APPLICATION_SCHEMA_MAX,
    APPLICATION_SCHEMA_MIN,
    MIGRATION_ADVISORY_LOCK_KEY,
    apply_migrations,
    assert_schema_compatible,
    migration_status,
)


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
            lock_timeout_ms=5_000,
            application_name="omnix-migration-contract-tests",
        )
    )


def test_migration_status_reports_application_compatibility() -> None:
    database = _database()
    try:
        apply_migrations(database)
        status = migration_status(database)

        assert status["compatible"] is True
        assert status["current_schema"] == status["discovered"][-1]
        assert APPLICATION_SCHEMA_MIN <= status["current_schema"] <= APPLICATION_SCHEMA_MAX
        assert status["application_schema_min"] == APPLICATION_SCHEMA_MIN
        assert status["application_schema_max"] == APPLICATION_SCHEMA_MAX
        assert_schema_compatible(status)
    finally:
        database.close()


def test_migration_advisory_lock_excludes_second_connection() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as first:
            first.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (MIGRATION_ADVISORY_LOCK_KEY,),
            )
            with database.connection() as second:
                acquired = second.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)",
                    (MIGRATION_ADVISORY_LOCK_KEY,),
                ).fetchone()[0]
                assert acquired is False

        with database.connection() as second:
            acquired = second.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (MIGRATION_ADVISORY_LOCK_KEY,),
            ).fetchone()[0]
            assert acquired is True
            second.execute(
                "SELECT pg_advisory_unlock(%s)",
                (MIGRATION_ADVISORY_LOCK_KEY,),
            )
            second.commit()
    finally:
        database.close()
