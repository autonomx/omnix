from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.security_audit import tenant_security_audit


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
            application_name="omnix-tenant-security-tests",
        )
    )


def test_tenant_security_audit_passes() -> None:
    database = _database()
    try:
        apply_migrations(database)
        bootstrap_local_tenant(database)
        with database.connection() as connection:
            report = tenant_security_audit(connection)
        assert report["ok"] is True
        assert report["missing_constraints"] == []
        assert report["policy"]["rls_decision"] == "deferred_local_only"
    finally:
        database.close()


def test_cross_workspace_chat_message_reference_is_rejected() -> None:
    database = _database()
    try:
        apply_migrations(database)
        local = bootstrap_local_tenant(database)
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) "
                "VALUES ('workspace:other', 'Other', %s) ON CONFLICT DO NOTHING",
                (local.user_id,),
            )
            connection.execute(
                """
                INSERT INTO omnix_chat_sessions (id, workspace_id, title)
                VALUES ('session:tenant-guard', %s, 'Guard')
                ON CONFLICT (id) DO NOTHING
                """,
                (local.workspace_id,),
            )
        with pytest.raises(Exception):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO omnix_chat_messages (
                        id, workspace_id, session_id, position, role, content
                    ) VALUES (
                        'message:cross-tenant', 'workspace:other',
                        'session:tenant-guard', 0, 'user', 'blocked'
                    )
                    """
                )
    finally:
        database.close()
