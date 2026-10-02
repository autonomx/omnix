from __future__ import annotations

import os
import shutil
from pathlib import Path
import uuid

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import (
    APPLICATION_SCHEMA_MAX,
    APPLICATION_SCHEMA_MIN,
    MIGRATION_ADVISORY_LOCK_KEY,
    MigrationDriftError,
    SchemaCompatibilityError,
    apply_migrations,
    assert_schema_compatible,
    migration_root,
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


def _future_migration_root(tmp_path: Path) -> Path:
    root = tmp_path / "future-migrations"
    root.mkdir()
    for migration in migration_root().glob("*.sql"):
        shutil.copyfile(migration, root / migration.name)
    return root


def _migration_sql(phase: str) -> str:
    return f"-- omnix-migration: phase={phase} transactional=true\nSELECT 1;\n"


def _remove_test_versions(database: PostgresDatabase, versions: tuple[str, ...]) -> None:
    with database.transaction() as connection:
        for version in versions:
            connection.execute(
                "DELETE FROM omnix_schema_migrations WHERE version = %s",
                (version,),
            )


def test_unknown_expand_is_compatible_and_unknown_contract_is_refused(tmp_path: Path) -> None:
    database = _database()
    suffix = uuid.uuid4().hex[:12]
    expand_version = f"9998_test_expand_{suffix}"
    contract_version = f"9999_test_contract_{suffix}"
    root = _future_migration_root(tmp_path)
    try:
        apply_migrations(database)

        (root / f"{expand_version}.sql").write_text(
            _migration_sql("expand"), encoding="utf-8"
        )
        apply_migrations(database, root=root)
        expand_status = migration_status(database)
        assert expand_version in expand_status["unknown_compatible"]
        assert expand_status["unknown_contract"] == []
        assert_schema_compatible(expand_status)

        _remove_test_versions(database, (expand_version,))
        (root / f"{contract_version}.sql").write_text(
            _migration_sql("contract"), encoding="utf-8"
        )
        apply_migrations(database, root=root)
        contract_status = migration_status(database)
        assert contract_version in contract_status["unknown_contract"]
        with pytest.raises(SchemaCompatibilityError, match="unknown_contract"):
            assert_schema_compatible(contract_status)
    finally:
        _remove_test_versions(database, (expand_version, contract_version))
        database.close()


def test_migration_runner_refuses_new_lower_sorting_pending_migration(tmp_path: Path) -> None:
    database = _database()
    suffix = uuid.uuid4().hex[:12]
    high_version = f"9999_test_high_{suffix}"
    low_version = f"9998_test_low_{suffix}"
    root = _future_migration_root(tmp_path)
    try:
        apply_migrations(database)
        (root / f"{high_version}.sql").write_text(
            _migration_sql("expand"), encoding="utf-8"
        )
        apply_migrations(database, root=root)
        (root / f"{low_version}.sql").write_text(
            _migration_sql("expand"), encoding="utf-8"
        )
        with pytest.raises(MigrationDriftError, match="out-of-order"):
            apply_migrations(database, root=root)
    finally:
        _remove_test_versions(database, (low_version, high_version))
        database.close()
