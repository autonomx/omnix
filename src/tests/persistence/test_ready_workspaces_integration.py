"""Job workers find the workspaces with work in one query, with no cap."""
from __future__ import annotations

import os
import secrets

import pytest

from app.jobs.models import CreateJobRequest, ResourceClass
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import (
    PostgresIdentityRepository,
    ensure_local_identity,
    list_active_workspace_contexts,
    list_workspace_contexts_with_ready_jobs,
)
from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
from app.runtime.tenant_context import pop_tenant, push_tenant
from tests.conftest_databases import is_disposable_test_database

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def database():
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    assert is_disposable_test_database(url)
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    try:
        yield database
    finally:
        database.close()


def _workspace(database, owner: str, label: str):
    workspace = f"workspace:ready-jobs:{label}:{secrets.token_urlsafe(8)}"
    with database.transaction() as connection:
        # Creating a workspace is a system operation (the runtime role is row-level secured).
        connection.execute("SELECT set_config('omnix.system', 'on', true)")
        connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, %s)",
                           (workspace, f"Ready jobs {label}", owner))
        connection.execute(
            "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
            (secrets.token_urlsafe(12), workspace, owner, ["owner", "admin", "member"]),
        )
        return PostgresIdentityRepository(connection).load_context(user_id=owner, workspace_id=workspace)


def _ready_job(database, context) -> None:
    """A claimable CPU job in the workspace, created as that workspace's tenant (jobs are row-level secured)."""
    store = PostgresJobStoreAdapter(database)
    store.context = context
    token = push_tenant(context)
    try:
        store.create_job(CreateJobRequest(module="diagnostics", type="diagnostics.ready", resource_class=ResourceClass.CPU))
    finally:
        pop_tenant(token)


def _delete(database, *workspaces: str) -> None:
    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', true)")
        connection.execute("DELETE FROM omnix_jobs WHERE workspace_id = ANY(%s)", (list(workspaces),))
        connection.execute("DELETE FROM omnix_workspace_memberships WHERE workspace_id = ANY(%s)", (list(workspaces),))
        connection.execute("DELETE FROM omnix_workspaces WHERE id = ANY(%s)", (list(workspaces),))


def test_only_workspaces_with_a_claimable_job_are_polled(database):
    owner = ensure_local_identity(database).user_id
    busy, idle = _workspace(database, owner, "busy"), _workspace(database, owner, "idle")
    try:
        _ready_job(database, busy)

        ready = {context.workspace_id for context in list_workspace_contexts_with_ready_jobs(database, ["cpu"])}
        assert busy.workspace_id in ready
        assert idle.workspace_id not in ready
        # Another pool's resource class sees nothing to claim there.
        gpu = {context.workspace_id for context in list_workspace_contexts_with_ready_jobs(database, ["gpu"])}
        assert busy.workspace_id not in gpu
        assert list_workspace_contexts_with_ready_jobs(database, []) == []
        # The contexts are system contexts, never request principals.
        context = next(c for c in list_workspace_contexts_with_ready_jobs(database, ["cpu"]) if c.workspace_id == busy.workspace_id)
        assert context.roles == frozenset({"system"})
        # The full listing has no silent cap.
        everyone = {c.workspace_id for c in list_active_workspace_contexts(database)}
        assert {busy.workspace_id, idle.workspace_id} <= everyone
    finally:
        _delete(database, busy.workspace_id, idle.workspace_id)


def test_the_longest_waiting_workspace_comes_first_under_the_limit(database):
    owner = ensure_local_identity(database).user_id
    older, newer = _workspace(database, owner, "older"), _workspace(database, owner, "newer")
    try:
        for context in (older, newer):
            _ready_job(database, context)
        with database.transaction() as connection:
            connection.execute("SELECT set_config('omnix.system', 'on', true)")
            connection.execute(
                "UPDATE omnix_jobs SET available_at = CURRENT_TIMESTAMP - INTERVAL '1 hour' WHERE workspace_id = %s",
                (older.workspace_id,),
            )
        listed = [c.workspace_id for c in list_workspace_contexts_with_ready_jobs(database, ["cpu"], limit=1000)]
        assert listed.index(older.workspace_id) < listed.index(newer.workspace_id)
        first = list_workspace_contexts_with_ready_jobs(database, ["cpu"], limit=1)
        assert len(first) == 1
    finally:
        _delete(database, older.workspace_id, newer.workspace_id)
