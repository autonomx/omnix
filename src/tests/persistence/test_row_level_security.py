"""PostgreSQL row-level security isolates workspaces (WP-4.4 acceptance).

The queries below deliberately omit any ``workspace_id`` filter: only the
database policies keep workspace B's rows away from workspace A.
"""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.tenant_scope import SYSTEM_OPERATIONS, session_scope, system_scope
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

PROBE_ROLE = "omnix_rls_probe"


def _admin() -> psycopg.Connection:
    return psycopg.connect(admin_database_url(), autocommit=True)


@pytest.fixture(scope="module")
def probe_role():
    """A runtime-like role: not superuser, not owner, no BYPASSRLS."""
    with _admin() as admin:
        if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.skip("creating the probe role needs a superuser test database")
        admin.execute(
            f"""DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN
                    CREATE ROLE {PROBE_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$"""
        )
        # A grant rewrites catalog rows; a parallel test's DDL can race it.
        for attempt in range(5):
            try:
                admin.execute(f"GRANT USAGE ON SCHEMA public TO {PROBE_ROLE}")
                admin.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PROBE_ROLE}")
                break
            except psycopg.errors.InternalError:
                if attempt == 4:
                    raise
    return PROBE_ROLE


@pytest.fixture
def two_workspaces():
    suffix = uuid.uuid4().hex[:10]
    a, b = f"workspace:rls-a-{suffix}", f"workspace:rls-b-{suffix}"
    with _admin() as admin:
        admin.execute(
            "INSERT INTO omnix_users (id, display_name) VALUES (%s, 'rls') ON CONFLICT DO NOTHING",
            ("user:rls",),
        )
        for workspace in (a, b):
            admin.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, 'user:rls')",
                (workspace, workspace),
            )
            admin.execute(
                "INSERT INTO omnix_settings_entries (workspace_id, key, value) VALUES (%s, 'rls.probe', %s::jsonb)",
                (workspace, f'"{workspace}"'),
            )
    try:
        yield a, b
    finally:
        with _admin() as admin:
            admin.execute("DELETE FROM omnix_workspaces WHERE id = ANY(%s)", ([a, b],))


def _as_probe(workspace_id: str, *, system: bool = False) -> psycopg.Connection:
    connection = psycopg.connect(admin_database_url(), autocommit=True)
    connection.execute(f"SET ROLE {PROBE_ROLE}")
    connection.execute(
        "SELECT set_config('omnix.workspace_id', %s, false), set_config('omnix.system', %s, false)",
        (workspace_id, "on" if system else ""),
    )
    return connection


def _visible_settings(connection: psycopg.Connection, workspaces: tuple[str, str]) -> set[str]:
    rows = connection.execute(
        "SELECT workspace_id FROM omnix_settings_entries WHERE key = 'rls.probe'"
    ).fetchall()
    return {row[0] for row in rows} & set(workspaces)


def test_raw_query_without_workspace_filter_sees_only_the_current_workspace(probe_role, two_workspaces):
    a, b = two_workspaces
    with _as_probe(a) as connection:
        assert _visible_settings(connection, two_workspaces) == {a}
        visible = {row[0] for row in connection.execute("SELECT id FROM omnix_workspaces").fetchall()}
        assert a in visible and b not in visible
    with _as_probe(b) as connection:
        assert _visible_settings(connection, two_workspaces) == {b}


def test_writes_with_another_workspace_id_are_rejected(probe_role, two_workspaces):
    a, b = two_workspaces
    with _as_probe(a) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO omnix_settings_entries (workspace_id, key, value) VALUES (%s, 'rls.other', '1'::jsonb)",
                (b,),
            )
        updated = connection.execute(
            "UPDATE omnix_settings_entries SET value = '2'::jsonb WHERE key = 'rls.probe' AND workspace_id = %s",
            (b,),
        )
        assert updated.rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE omnix_settings_entries SET workspace_id = %s WHERE key = 'rls.probe' AND workspace_id = %s",
                (b, a),
            )


def test_session_without_tenant_sees_nothing_and_system_scope_sees_everything(probe_role, two_workspaces):
    with _as_probe("") as connection:
        assert _visible_settings(connection, two_workspaces) == set()
    with _as_probe("", system=True) as connection:
        assert _visible_settings(connection, two_workspaces) == set(two_workspaces)


def test_child_tables_follow_their_parent_row(probe_role, two_workspaces):
    a, b = two_workspaces
    asset_id = f"asset:rls-{uuid.uuid4().hex[:10]}"
    with _admin() as admin:
        admin.execute(
            """INSERT INTO omnix_assets
                   (id, workspace_id, module, asset_type, mime_type, byte_size, checksum_sha256, storage_provider, storage_key)
               VALUES (%s, %s, 'test', 'image', 'image/png', 1, %s, 'local', %s)""",
            (asset_id, b, "0" * 64, asset_id),
        )
        admin.execute(
            """INSERT INTO omnix_asset_versions (asset_id, version, checksum_sha256, byte_size, storage_provider, storage_key)
               VALUES (%s, 1, %s, 1, 'local', %s)""",
            (asset_id, "0" * 64, asset_id),
        )
    with _as_probe(a) as connection:
        assert connection.execute(
            "SELECT count(*) FROM omnix_asset_versions WHERE asset_id = %s", (asset_id,)
        ).fetchone()[0] == 0
    with _as_probe(b) as connection:
        assert connection.execute(
            "SELECT count(*) FROM omnix_asset_versions WHERE asset_id = %s", (asset_id,)
        ).fetchone()[0] == 1


def test_pool_checkout_applies_the_current_tenant(two_workspaces):
    a, b = two_workspaces
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=1))
    context = TenantContext(user_id="user:rls", workspace_id=b, membership_id="m", roles=frozenset({"owner"}))
    try:
        token = push_tenant(context)
        try:
            assert session_scope() == (b, "")
            with database.connection() as connection:
                assert connection.execute(
                    "SELECT current_setting('omnix.workspace_id', true), current_setting('omnix.system', true)"
                ).fetchone() == (b, "")
                connection.rollback()
            with system_scope("identity.workspaces"), database.connection() as connection:
                assert connection.execute(
                    "SELECT current_setting('omnix.workspace_id', true), current_setting('omnix.system', true)"
                ).fetchone() == (b, "on")
                connection.rollback()
        finally:
            pop_tenant(token)
        # The same pooled session is re-scoped for the next tenant.
        token = push_tenant(TenantContext(user_id="user:rls", workspace_id=a, membership_id="m", roles=frozenset({"owner"})))
        try:
            with database.connection() as connection:
                assert connection.execute("SELECT current_setting('omnix.workspace_id', true)").fetchone() == (a,)
                connection.rollback()
        finally:
            pop_tenant(token)
    finally:
        database.close()


def test_system_scope_requires_a_listed_operation():
    with pytest.raises(ValueError):
        with system_scope("anything"):
            pass
    assert all(reason.strip() for reason in SYSTEM_OPERATIONS.values())


def test_every_tenant_table_enforces_row_level_security():
    """A new table with workspace_id must ship with a tenant_isolation policy."""
    with _admin() as admin:
        rows = admin.execute(
            """
            SELECT relation.relname, relation.relrowsecurity, relation.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies AS policy
                            WHERE policy.tablename = relation.relname AND policy.policyname = 'tenant_isolation')
              FROM pg_class AS relation
              JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname = 'public' AND relation.relkind = 'r'
               AND relation.relname LIKE 'omnix_%%'
               AND EXISTS (SELECT 1 FROM pg_attribute AS attribute
                            WHERE attribute.attrelid = relation.oid AND attribute.attname = 'workspace_id'
                              AND attribute.attnum > 0 AND NOT attribute.attisdropped)
            """
        ).fetchall()
    assert len(rows) > 100
    missing = sorted(row[0] for row in rows if not (row[1] and row[2] and row[3]))
    assert not missing, f"tenant tables without row-level security: {missing}"
