"""Two users in two workspaces are isolated at the API level (WP-4.2 acceptance)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.tenant_scope import system_scope
from app.persistence.unit_of_work import unit_of_work
from app.security.auth import AuthenticatedPrincipal
from tests.support.auth import FakeAuthenticator
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def database():
    db = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    ensure_local_identity(db)
    try:
        yield db
    finally:
        db.close()


def _workspace_with_member(database: PostgresDatabase, label: str):
    suffix = uuid.uuid4().hex[:10]
    user_id, workspace_id = f"user:{label}-{suffix}", f"workspace:{label}-{suffix}"
    with system_scope("identity.provision"), unit_of_work(database) as work:
        work.connection.execute(
            "INSERT INTO omnix_users (id, display_name) VALUES (%s, %s)", (user_id, label)
        )
        work.connection.execute(
            "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, %s)",
            (workspace_id, f"{label} workspace", user_id),
        )
        context = work.identities.provision_member(
            user_id=user_id, display_name=label, email=None, workspace_id=workspace_id, roles=("owner",)
        )
        work.commit()
    return context


def _resolver(database: PostgresDatabase):
    def resolve(user_id: str, workspace_id: str):
        with unit_of_work(database) as work:
            try:
                return work.identities.load_context(user_id=user_id, workspace_id=workspace_id)
            finally:
                work.rollback()

    return resolve


def _client(app, token: str, **headers: str) -> TestClient:
    client = TestClient(
        app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test", **headers}
    )
    client.cookies.set("omnix_session", token)
    return client


def _submit_probe(client: TestClient, csrf: str) -> str:
    response = client.post(
        "/api/jobs",
        json={"module": "platform", "type": "platform.probe", "resource_class": "cpu",
              "input_payload": {"duration_ms": 1, "label": "isolation"}},
        headers={"X-Omnix-CSRF": csrf},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def test_two_users_in_two_workspaces_cannot_see_each_others_jobs(database) -> None:
    from app.gateway.main import create_gateway_app
    from app.persistence.job_compat import PostgresJobStoreAdapter

    alice = _workspace_with_member(database, "alice")
    bob = _workspace_with_member(database, "bob")
    authenticator = FakeAuthenticator()
    tokens = {}
    for name, context in (("alice", alice), ("bob", bob)):
        token, csrf = authenticator.issue_session(user_id=context.user_id)
        principal = authenticator.sessions[token]
        authenticator.sessions[token] = AuthenticatedPrincipal(
            user_id=context.user_id, context=context, auth_method=principal.auth_method,
            session_id=principal.session_id, csrf_token=csrf,
        )
        tokens[name] = (token, csrf)

    # One process-wide store, as in production: it must follow each request.
    store = PostgresJobStoreAdapter(database=database)
    app = create_gateway_app(
        job_store_factory=lambda: store,
        auth_service=authenticator,
        membership_resolver=_resolver(database),
    )
    alice_client = _client(app, tokens["alice"][0])
    bob_client = _client(app, tokens["bob"][0])

    alice_job = _submit_probe(alice_client, tokens["alice"][1])
    bob_job = _submit_probe(bob_client, tokens["bob"][1])

    alice_ids = {job["id"] for job in alice_client.get("/api/jobs", params={"limit": 200}).json()["jobs"]}
    bob_ids = {job["id"] for job in bob_client.get("/api/jobs", params={"limit": 200}).json()["jobs"]}
    assert alice_job in alice_ids and bob_job not in alice_ids
    assert bob_job in bob_ids and alice_job not in bob_ids
    assert bob_client.get(f"/api/jobs/{alice_job}").status_code == 404

    # Read storage directly as the DDL owner: the runtime role only sees its
    # current workspace (row-level security, WP-4.4).
    with psycopg.connect(admin_database_url()) as admin:
        stored = dict(admin.execute(
            "SELECT id, workspace_id FROM omnix_jobs WHERE id = ANY(%s)", ([alice_job, bob_job],)
        ).fetchall())
    assert stored == {alice_job: alice.workspace_id, bob_job: bob.workspace_id}

    # Naming another workspace never widens access.
    denied = _client(app, tokens["bob"][0], **{"X-Omnix-Workspace": alice.workspace_id}).get("/api/jobs")
    assert denied.status_code == 403
    assert denied.json() == {"detail": "workspace_access_denied"}
    explicit = _client(app, tokens["alice"][0], **{"X-Omnix-Workspace": alice.workspace_id}).get("/api/jobs")
    assert explicit.status_code == 200
