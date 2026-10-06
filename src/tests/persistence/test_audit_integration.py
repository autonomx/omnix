"""The audit trail is append-only (WP-4.8 acceptance)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.persistence.audit import PostgresAuditSink
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.security.audit import AuditEvent
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def workspace():
    suffix = uuid.uuid4().hex[:10]
    workspace_id = f"workspace:audit-{suffix}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("INSERT INTO omnix_users (id, display_name) VALUES ('user:audit', 'audit') ON CONFLICT DO NOTHING")
        admin.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, 'user:audit')",
                      (workspace_id, workspace_id))
    yield workspace_id
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))


def _write(workspace_id: str, *, actor: str) -> int:
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=1))
    marker = uuid.uuid4().hex
    try:
        PostgresAuditSink(database).write(AuditEvent(
            action="settings.update", target_type="setting", target_id=marker, outcome="success",
            workspace_id=workspace_id, actor_user_id=actor, details={"method": "POST"},
        ))
    finally:
        database.close()
    with psycopg.connect(admin_database_url()) as admin:
        return int(admin.execute("SELECT id FROM omnix_audit_events WHERE aggregate_id = %s", (marker,)).fetchone()[0])


def test_audit_rows_cannot_be_changed_or_deleted(workspace) -> None:
    event_id = _write(workspace, actor="user:audit")
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            admin.execute("UPDATE omnix_audit_events SET action = 'x' WHERE id = %s", (event_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            admin.execute("DELETE FROM omnix_audit_events WHERE id = %s", (event_id,))
        row = admin.execute("SELECT actor_user_id, payload FROM omnix_audit_events WHERE id = %s", (event_id,)).fetchone()
    assert row[0] == "user:audit"
    assert row[1]["outcome"] == "success"


def test_unknown_actors_are_kept_in_the_payload(workspace) -> None:
    event_id = _write(workspace, actor="agent-run:demo")
    with psycopg.connect(admin_database_url()) as admin:
        actor, payload = admin.execute(
            "SELECT actor_user_id, payload FROM omnix_audit_events WHERE id = %s", (event_id,)
        ).fetchone()
    assert actor is None
    assert payload["actor"] == "agent-run:demo"


def test_deleting_a_workspace_keeps_its_audit_rows() -> None:
    workspace_id = f"workspace:audit-gone-{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("INSERT INTO omnix_users (id, display_name) VALUES ('user:audit', 'audit') ON CONFLICT DO NOTHING")
        admin.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, 'user:audit')",
                      (workspace_id, workspace_id))
    event_id = _write(workspace_id, actor="user:audit")
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        assert admin.execute("SELECT workspace_id FROM omnix_audit_events WHERE id = %s",
                             (event_id,)).fetchone() == (None,)


def test_runtime_role_cannot_delete_audit_rows(workspace) -> None:
    event_id = _write(workspace, actor="user:audit")
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.skip("the probe role needs a superuser test database")
        admin.execute("""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omnix_rls_probe') THEN
                CREATE ROLE omnix_rls_probe NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF; END $$""")
        admin.execute("GRANT SELECT, DELETE ON omnix_audit_events TO omnix_rls_probe")
        admin.execute("SET ROLE omnix_rls_probe")
        admin.execute("SELECT set_config('omnix.system', 'on', false)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            admin.execute("DELETE FROM omnix_audit_events WHERE id = %s", (event_id,))
