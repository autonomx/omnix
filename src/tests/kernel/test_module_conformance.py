"""Every catalog module conforms to the module anatomy, up to the shrinking baseline (ADR-0016, PA-4.1)."""
from __future__ import annotations

import dataclasses
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

from scripts import module_conformance as conformance


def test_static_gaps_match_the_baseline_exactly() -> None:
    # A new gap fails; a fixed gap fails until its baseline entry is deleted.
    assert conformance.static_gaps() == conformance.load_baseline()["modules"]


def _status(**tables: dict) -> dict[str, dict]:
    defaults = {"rls": True, "forced": True, "comment": "", "policies": 1, "foreign_keys": set()}
    return {name: {**defaults, **entry} for name, entry in tables.items()}


WORKSPACE = ("((workspace_id = current_setting('omnix.workspace_id'::text, true)) "
             "OR (current_setting('omnix.system'::text, true) = 'on'::text))")
CHILD = "(EXISTS ( SELECT 1 FROM omnix_parent parent WHERE (parent.id = omnix_child.parent_id)))"


def test_a_workspace_table_with_the_0106_policy_is_isolated() -> None:
    status = _status(omnix_parent={"using": WORKSPACE, "check": WORKSPACE})

    assert conformance.isolated("omnix_parent", status)


@pytest.mark.parametrize("change", [
    {"forced": False},
    {"rls": False},
    {"using": "true", "check": "true"},
    {"policies": 2},
])
def test_anything_short_of_the_policy_is_not_isolated(change: dict) -> None:
    status = _status(omnix_parent={"using": WORKSPACE, "check": WORKSPACE, **change})

    assert not conformance.isolated("omnix_parent", status)


def test_a_child_is_isolated_through_its_declared_foreign_key_to_an_isolated_parent() -> None:
    parent = {"using": WORKSPACE, "check": WORKSPACE}
    child = {"using": CHILD, "check": CHILD, "foreign_keys": {("parent_id", "omnix_parent", "id")}}

    assert conformance.isolated("omnix_child", _status(omnix_parent=parent, omnix_child=child))
    assert not conformance.isolated("omnix_child", _status(omnix_parent=parent, omnix_child={**child, "foreign_keys": set()}))
    assert not conformance.isolated("omnix_child", _status(omnix_parent={**parent, "forced": False}, omnix_child=child))


def _fresh_database_url() -> str:
    base = os.environ.get("OMNIX_TEST_DATABASE_URL")
    if not base:
        pytest.skip("OMNIX_TEST_DATABASE_URL is required")
    admin = os.environ.get("OMNIX_TEST_ADMIN_DATABASE_URL") or os.environ.get("OMNIX_MIGRATION_DATABASE_URL") or base
    return urlunsplit(urlsplit(admin)._replace(path=f"/omnix_conformance_{uuid.uuid4().hex[:8]}"))


@pytest.mark.postgres
def test_tenant_isolation_gaps_on_a_freshly_migrated_database_match_the_baseline() -> None:
    import psycopg

    from app.persistence.database import PostgresDatabase, database_settings
    from app.persistence.migrations import apply_migrations

    url = _fresh_database_url()
    name = urlsplit(url).path.lstrip("/")
    maintenance = urlunsplit(urlsplit(url)._replace(path="/postgres"))
    try:
        with psycopg.connect(maintenance, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
    except psycopg.errors.InsufficientPrivilege:
        pytest.skip("the test role cannot create databases; set OMNIX_TEST_ADMIN_DATABASE_URL")
    try:
        database = PostgresDatabase(dataclasses.replace(database_settings(), url=url, pool_min=1, pool_max=2))
        apply_migrations(database)
        database.close()
        owners, historical = conformance.table_owners_and_historical()
        with psycopg.connect(url) as connection:
            gaps = conformance.tenant_gaps(connection, owners, historical)
            exempt = conformance.exemptions(connection, owners, historical)
    finally:
        with psycopg.connect(maintenance, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    assert gaps == conformance.load_baseline()["tenant_isolation"]
    # Every exemption carries its reason; the report lists them.
    assert exempt and all(reason.strip() for reason in exempt.values())
