from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import IdempotencyConflict, RevisionConflict
from app.persistence.identity_service import (
    bootstrap_local_tenant,
    get_workspace,
    rename_workspace,
)
from app.persistence.migrations import apply_migrations
from app.persistence.tenant import TenantAccessDenied
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-identity-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_local_bootstrap_is_idempotent_and_tenant_scoped() -> None:
    database = _database()
    try:
        _reset(database)
        first = bootstrap_local_tenant(database)
        second = bootstrap_local_tenant(database)
        assert first == second
        workspace = get_workspace(database, first)
        assert workspace["id"] == first.workspace_id
        assert workspace["revision"] == 1
        with database.connection() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_users), "
                "(SELECT COUNT(*) FROM omnix_workspaces), "
                "(SELECT COUNT(*) FROM omnix_workspace_memberships)"
            ).fetchone()
        assert tuple(int(value) for value in counts) == (1, 1, 1)
    finally:
        database.close()


def test_workspace_rename_is_revisioned_and_idempotent() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        first = rename_workspace(
            database,
            context,
            name="Primary Workspace",
            expected_revision=1,
            operation_key="rename:one",
        )
        replay = rename_workspace(
            database,
            context,
            name="Primary Workspace",
            expected_revision=1,
            operation_key="rename:one",
        )
        assert first == replay
        assert first["revision"] == 2

        with pytest.raises(RevisionConflict):
            rename_workspace(
                database,
                context,
                name="Stale Writer",
                expected_revision=1,
                operation_key="rename:stale",
            )
        with pytest.raises(IdempotencyConflict):
            rename_workspace(
                database,
                context,
                name="Different Input",
                expected_revision=1,
                operation_key="rename:one",
            )
        with database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM omnix_audit_events "
                "WHERE action = 'workspace.renamed'"
            ).fetchone()[0]
        assert int(count) == 1
    finally:
        database.close()


def test_cross_workspace_access_is_denied() -> None:
    database = _database()
    try:
        _reset(database)
        local = bootstrap_local_tenant(database)
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_users (id, display_name) VALUES (%s, %s)",
                ("user:other", "Other User"),
            )
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, %s)",
                ("workspace:other", "Other Workspace", "user:other"),
            )
            connection.execute(
                "INSERT INTO omnix_workspace_memberships "
                "(id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
                (
                    "membership:other",
                    "workspace:other",
                    "user:other",
                    ["owner"],
                ),
            )
        with unit_of_work(database) as work:
            with pytest.raises(TenantAccessDenied):
                work.identities.get_workspace(local, "workspace:other")
            work.rollback()
    finally:
        database.close()


def test_uncommitted_unit_of_work_rolls_back() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.audit.append(
                context,
                aggregate_type="probe",
                aggregate_id="probe:rollback",
                action="probe.uncommitted",
            )
        with database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM omnix_audit_events "
                "WHERE aggregate_id = 'probe:rollback'"
            ).fetchone()[0]
        assert int(count) == 0
    finally:
        database.close()
