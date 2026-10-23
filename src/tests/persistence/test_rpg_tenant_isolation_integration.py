"""Two users in two workspaces cannot see or play each other's RPG campaigns (RQ-8.3, PostgreSQL)."""
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
        work.connection.execute("INSERT INTO omnix_users (id, display_name) VALUES (%s, %s)", (user_id, label))
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


def _client(app, token: str, csrf: str, **headers: str) -> TestClient:
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test", "X-Omnix-CSRF": csrf, **headers},
    )
    client.cookies.set("omnix_session", token)
    return client


def _new_game(client: TestClient, seed: int) -> str:
    response = client.post(
        "/api/rpg/new-game",
        json={
            "campaign_template": "classic_fantasy",
            "tone": "heroic adventure",
            "starting_location": "rusty_flagon_tavern",
            "seed": seed,
        },
    )
    assert response.status_code == 200, response.text[:800]
    body = response.json()
    session_id = str(body.get("session_id") or (body.get("game") or {}).get("manifest", {}).get("session_id") or "")
    assert session_id, body
    return session_id


def _listed(client: TestClient) -> set[str]:
    response = client.get("/api/rpg/sessions")
    assert response.status_code == 200, response.text[:500]
    body = response.json()
    return {str((row.get("manifest") or {}).get("session_id") or "") for row in body["sessions"]}


def test_two_users_in_two_workspaces_cannot_see_or_play_each_others_campaigns(database) -> None:
    from app.composition.gateway.main import create_gateway_app
    from app.persistence.startup import bootstrap_postgresql_runtime

    bootstrap_postgresql_runtime()
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
    app = create_gateway_app(auth_service=authenticator, membership_resolver=_resolver(database))
    alice_client = _client(app, *tokens["alice"])
    bob_client = _client(app, *tokens["bob"])

    alice_game = _new_game(alice_client, 7)
    bob_game = _new_game(bob_client, 8)

    assert alice_game in _listed(alice_client) and bob_game not in _listed(alice_client)
    assert bob_game in _listed(bob_client) and alice_game not in _listed(bob_client)
    assert alice_client.get(f"/api/rpg/sessions/{alice_game}").status_code == 200

    # Every read and write of another workspace's campaign is refused as if it did not exist.
    probes = (
        ("get", f"/api/rpg/sessions/{alice_game}", None),
        ("get", f"/api/rpg/sessions/{alice_game}/lore", None),
        ("post", f"/api/rpg/sessions/{alice_game}/turn", {"command": "look around"}),
        ("post", f"/api/rpg/sessions/{alice_game}/rename", {"name": "Mine now"}),
        ("post", f"/api/rpg/sessions/{alice_game}/loadout-action", {"action": "equip", "item_name": "Dagger"}),
        ("post", f"/api/rpg/sessions/{alice_game}/delete", {}),
    )
    for method, path, body in probes:
        response = getattr(bob_client, method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code in {403, 404}, (method, path, response.status_code, response.text[:300])

    # A turn draft is scoped to the user who submitted the turn: another user reads nothing.
    draft = bob_client.get(f"/api/rpg/sessions/{alice_game}/turn-draft", params={"submission_id": "probe"})
    assert draft.status_code in {200, 403, 404}
    if draft.status_code == 200:
        assert draft.json() == {"text": "", "done": False, "found": False}

    # Alice's campaign is untouched, and storage records each campaign in its own workspace.
    assert alice_client.get(f"/api/rpg/sessions/{alice_game}").status_code == 200
    with psycopg.connect(admin_database_url()) as admin:
        stored = dict(admin.execute(
            "SELECT id, workspace_id FROM omnix_rpg_campaigns WHERE id = ANY(%s)", ([alice_game, bob_game],)
        ).fetchall())
        turns = admin.execute(
            "SELECT count(*) FROM omnix_rpg_turns WHERE campaign_id = %s", (alice_game,)
        ).fetchone()[0]
    assert stored == {alice_game: alice.workspace_id, bob_game: bob.workspace_id}
    assert turns == 0

    # Naming another workspace never widens access.
    denied = _client(app, *tokens["bob"], **{"X-Omnix-Workspace": alice.workspace_id}).get("/api/rpg/sessions")
    assert denied.status_code == 403
