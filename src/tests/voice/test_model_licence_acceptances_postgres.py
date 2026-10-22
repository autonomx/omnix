"""Recorded licence acceptances over real PostgreSQL (desktop roadmap D-4, migration 0168)."""
from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="requires disposable PostgreSQL test database"),
]

REVISION = "0123456789abcdef0123456789abcdef01234567"


def _entry(model_id: str, revision: str = REVISION) -> SimpleNamespace:
    return SimpleNamespace(id=model_id, revision=revision,
                           licence=SimpleNamespace(id="Apache-2.0", url="https://example.com/licence"))


@pytest.fixture
def two_workspaces():
    from app.persistence import database as database_module
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
    from app.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.tenant_scope import system_scope

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=4))
    ensure_local_identity(database)
    user = PostgresJobStoreAdapter(database).context.user_id
    ids = [f"workspace:licences:{uuid.uuid4().hex}" for _ in range(2)]
    contexts = []
    with system_scope("identity.provision"), database.transaction() as connection:
        for workspace_id in ids:
            connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Licence test', %s)",
                               (workspace_id, user))
            connection.execute(
                "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
                (f"membership:{uuid.uuid4().hex}", workspace_id, user, ["owner"]),
            )
            contexts.append(PostgresIdentityRepository(connection).load_context(user_id=user, workspace_id=workspace_id))
    original = database_module.default_database
    database_module.default_database = lambda: database  # type: ignore[assignment]
    try:
        yield database, contexts
    finally:
        database_module.default_database = original  # type: ignore[assignment]
        with system_scope("identity.provision"), database.transaction() as connection:
            for workspace_id in ids:
                connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        database.close()


def test_an_acceptance_counts_in_its_workspace_and_revision_only(two_workspaces) -> None:
    from app.platform.voice import licence_acceptances
    from app.runtime.tenant_context import pop_tenant, push_tenant

    _, (first, second) = two_workspaces
    token = push_tenant(first)
    try:
        assert licence_acceptances.record([_entry("tts-model")]) == 1
        licence_acceptances.record([_entry("tts-model")])  # recording twice is harmless
        assert licence_acceptances.accepted("tts-model", REVISION, "Apache-2.0")
        assert not licence_acceptances.accepted("tts-model", REVISION, "CC-BY-NC-4.0")  # the licence changed
        # A catalog update that pins another revision needs a new acceptance.
        assert not licence_acceptances.accepted("tts-model", "f" * 40, "Apache-2.0")
        assert licence_acceptances.accepted_models() == {"tts-model": {(REVISION, "Apache-2.0")}}
    finally:
        pop_tenant(token)
    token = push_tenant(second)
    try:
        assert not licence_acceptances.accepted("tts-model", REVISION, "Apache-2.0")
        assert licence_acceptances.accepted_models() == {}
    finally:
        pop_tenant(token)


def test_the_acceptance_table_enforces_row_level_security(two_workspaces) -> None:
    database, (first, second) = two_workspaces
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'omnix_model_licence_acceptances'"
        ).fetchone()
    assert row == (True, True)
