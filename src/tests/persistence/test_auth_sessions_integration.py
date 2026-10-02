from __future__ import annotations

import dataclasses
import os
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.security.auth import AuthService, resolve_auth_settings
from tests.support.fake_oidc import API_AUDIENCE, FakeIdentityProvider, oidc_settings

# The install credential is a singleton row and rotation signs out every local
# session, so this module runs on one xdist worker.
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.xdist_group("auth-install-credential"),
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def database():
    db = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-auth-tests",
        )
    )
    ensure_local_identity(db)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def local_auth(database):
    service = AuthService(resolve_auth_settings({"OMNIX_AUTH_MODE": "local"}), database=database)
    credential = secrets.token_urlsafe(32)
    service.sync_install_credential(credential)
    return service, credential


def _audit_actions(database, since_id: int) -> list[str]:
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT action FROM omnix_audit_events WHERE id > %s AND action LIKE 'auth.%%' ORDER BY id",
            (since_id,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _audit_cursor(database) -> int:
    with database.connection() as connection:
        return int(connection.execute("SELECT COALESCE(MAX(id), 0) FROM omnix_audit_events").fetchone()[0])


def test_install_credential_login_issues_session_and_audits(database, local_auth) -> None:
    service, credential = local_auth
    cursor = _audit_cursor(database)

    assert service.login_with_install_credential("wrong-" + credential, user_agent="pytest") is None
    issued = service.login_with_install_credential(credential, user_agent="pytest")
    assert issued is not None
    assert issued.principal.user_id == "user:local"
    assert "owner" in issued.principal.context.roles

    principal = service.authenticate_session(issued.token)
    assert principal is not None
    assert principal.csrf_token == issued.csrf_token
    assert principal.session_id is not None
    # Only the digest is stored, never the cookie value.
    with database.connection() as connection:
        stored = connection.execute(
            "SELECT count(*) FROM omnix_auth_sessions WHERE id = %s", (issued.token,)
        ).fetchone()[0]
    assert stored == 0
    assert _audit_actions(database, cursor) == ["auth.failed", "auth.login"]


def test_login_code_is_single_use_and_expires(database, local_auth) -> None:
    service, _ = local_auth
    code = service.issue_login_code()
    issued = service.exchange_login_code(code, user_agent=None)
    assert issued is not None
    assert service.exchange_login_code(code, user_agent=None) is None

    expired = service.issue_login_code()
    with database.connection() as connection:
        connection.execute(
            "UPDATE omnix_auth_login_codes SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' "
            "WHERE consumed_at IS NULL"
        )
        connection.commit()
    assert service.exchange_login_code(expired, user_agent=None) is None


def test_logout_revokes_the_session(database, local_auth) -> None:
    service, credential = local_auth
    issued = service.login_with_install_credential(credential, user_agent=None)
    assert issued is not None
    cursor = _audit_cursor(database)
    service.logout(issued.token)
    assert service.authenticate_session(issued.token) is None
    assert _audit_actions(database, cursor) == ["auth.logout"]


@pytest.mark.parametrize(
    "assignment",
    [
        "expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'",
        # The schema keeps expires_at <= absolute_expires_at, so both move.
        "expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second', "
        "absolute_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'",
    ],
    ids=["idle", "absolute"],
)
def test_idle_and_absolute_expiry_end_the_session(database, local_auth, assignment) -> None:
    service, credential = local_auth
    issued = service.login_with_install_credential(credential, user_agent=None)
    assert issued is not None and issued.principal.session_id is not None
    with database.connection() as connection:
        connection.execute(
            f"UPDATE omnix_auth_sessions SET {assignment} WHERE id = %s",
            (issued.principal.session_id,),
        )
        connection.commit()
    assert service.authenticate_session(issued.token) is None


def test_sliding_expiry_extends_but_never_past_the_absolute_limit(database, local_auth) -> None:
    service, credential = local_auth
    issued = service.login_with_install_credential(credential, user_agent=None)
    assert issued is not None
    session_id = issued.principal.session_id
    with database.connection() as connection:
        connection.execute(
            """
            UPDATE omnix_auth_sessions
               SET last_seen_at = CURRENT_TIMESTAMP - INTERVAL '2 hours',
                   expires_at = CURRENT_TIMESTAMP + INTERVAL '1 minute',
                   absolute_expires_at = CURRENT_TIMESTAMP + INTERVAL '30 minutes'
             WHERE id = %s
            """,
            (session_id,),
        )
        connection.commit()
    assert service.authenticate_session(issued.token) is not None
    with database.connection() as connection:
        expires, absolute = connection.execute(
            "SELECT expires_at, absolute_expires_at FROM omnix_auth_sessions WHERE id = %s",
            (session_id,),
        ).fetchone()
    assert expires == absolute


def test_install_credential_rotation_signs_out_every_local_session(database, local_auth) -> None:
    service, credential = local_auth
    issued = service.login_with_install_credential(credential, user_agent=None)
    assert issued is not None
    assert service.sync_install_credential(credential) is False
    replacement = secrets.token_urlsafe(32)
    assert service.sync_install_credential(replacement) is True
    assert service.authenticate_session(issued.token) is None
    assert service.login_with_install_credential(credential, user_agent=None) is None
    assert service.login_with_install_credential(replacement, user_agent=None) is not None


def _oidc_service(database, idp: FakeIdentityProvider, **overrides) -> AuthService:
    settings = dataclasses.replace(
        resolve_auth_settings({"OMNIX_AUTH_MODE": "local"}),
        mode=resolve_auth_settings({}).mode.__class__("oidc"),
        oidc=oidc_settings(**overrides),
    )
    return AuthService(settings, database=database, oidc=idp.client(settings.oidc))


def _oidc_login(service: AuthService, idp: FakeIdentityProvider, claims: dict, *, next_path: str = "/"):
    url, binding = service.start_oidc_login(redirect_after=next_path)
    code, state = idp.authorize(url, claims)
    return service.complete_oidc_login(code=code, state=state, browser_binding=binding, user_agent=None), (
        url,
        binding,
        state,
    )


def test_oidc_login_provisions_a_member_and_maps_returning_users(database) -> None:
    idp = FakeIdentityProvider()
    service = _oidc_service(database, idp)
    subject = f"alice-{uuid.uuid4().hex}"
    claims = {"sub": subject, "email": "alice@example.com", "email_verified": True, "name": "Alice"}

    first, _ = _oidc_login(service, idp, claims, next_path="/chat")
    assert first is not None
    issued, redirect_after = first
    assert redirect_after == "/chat"
    assert issued.principal.context.roles == frozenset({"member"})
    assert issued.principal.user_id.startswith("user:oidc:")

    second, _ = _oidc_login(service, idp, claims)
    assert second is not None
    assert second[0].principal.user_id == issued.principal.user_id
    assert service.authenticate_session(second[0].token) is not None

    # A different subject presenting the same email is a different account.
    impostor, _ = _oidc_login(service, idp, {**claims, "sub": f"other-{uuid.uuid4().hex}"})
    assert impostor is not None
    assert impostor[0].principal.user_id != issued.principal.user_id


def test_oidc_state_is_bound_to_the_browser_and_single_use(database) -> None:
    idp = FakeIdentityProvider()
    service = _oidc_service(database, idp)
    url, binding = service.start_oidc_login(redirect_after="/")
    code, state = idp.authorize(url, {"sub": f"bob-{uuid.uuid4().hex}"})
    # Another browser (login CSRF) cannot complete this transaction.
    assert service.complete_oidc_login(code=code, state=state, browser_binding="attacker", user_agent=None) is None
    assert service.complete_oidc_login(code=code, state=state, browser_binding=binding, user_agent=None) is not None
    assert service.complete_oidc_login(code=code, state=state, browser_binding=binding, user_agent=None) is None


def test_oidc_admission_rules_block_provisioning(database) -> None:
    idp = FakeIdentityProvider()
    service = _oidc_service(database, idp, allowed_domains=("example.com",))
    result, _ = _oidc_login(
        service, idp, {"sub": f"eve-{uuid.uuid4().hex}", "email": "eve@evil.example", "email_verified": True}
    )
    assert result is None


def test_oidc_bearer_tokens_map_only_known_identities(database) -> None:
    idp = FakeIdentityProvider()
    service = _oidc_service(database, idp)
    subject = f"carol-{uuid.uuid4().hex}"
    stranger = idp.sign({"sub": subject, "aud": API_AUDIENCE})
    assert service.authenticate_bearer(stranger) is None

    result, _ = _oidc_login(service, idp, {"sub": subject})
    assert result is not None
    principal = service.authenticate_bearer(idp.sign({"sub": subject, "aud": API_AUDIENCE}))
    assert principal is not None
    assert principal.user_id == result[0].principal.user_id
    assert principal.auth_method == "bearer"


def test_disabled_membership_ends_existing_sessions(database) -> None:
    idp = FakeIdentityProvider()
    service = _oidc_service(database, idp)
    result, _ = _oidc_login(service, idp, {"sub": f"dave-{uuid.uuid4().hex}"})
    assert result is not None
    issued = result[0]
    with database.connection() as connection:
        connection.execute(
            "UPDATE omnix_workspace_memberships SET status = 'disabled' WHERE user_id = %s",
            (issued.principal.user_id,),
        )
        connection.commit()
    assert service.authenticate_session(issued.token) is None


def test_launcher_login_flow_through_the_gateway(database, local_auth, monkeypatch) -> None:
    from app.gateway.main import create_gateway_app

    service, _ = local_auth
    app = create_gateway_app(auth_service=service)
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test"},
        follow_redirects=False,
    )
    assert client.get("/api/auth/session").json()["authenticated"] is False

    expired = client.get("/api/auth/local/callback", params={"code": "bogus"})
    assert expired.status_code == 303
    assert expired.headers["location"] == "/login?error=login_link_expired"

    callback = client.get(
        "/api/auth/local/callback",
        params={"code": service.issue_login_code(), "next": "https://evil.example/"},
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/"
    cookies = callback.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("omnix_session="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    csrf_cookie = next(value for value in cookies if value.startswith("omnix_csrf="))
    assert "HttpOnly" not in csrf_cookie

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user_id"] == "user:local"
    csrf = client.cookies.get("omnix_csrf")

    assert client.post("/api/__auth_probe__").status_code == 403
    assert client.post("/api/__auth_probe__", headers={"X-Omnix-CSRF": csrf}).status_code in {404, 405}

    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-Omnix-CSRF": csrf}).status_code == 204
    client.cookies.clear()
    assert client.get("/api/auth/session").json()["authenticated"] is False
    assert client.get("/api/__auth_probe__").status_code == 401


def test_manual_login_rotates_any_presented_session(database, local_auth) -> None:
    from app.gateway.main import create_gateway_app

    service, credential = local_auth
    client = TestClient(
        create_gateway_app(auth_service=service),
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test"},
    )
    assert client.post("/api/auth/local/login", json={"credential": "nope"}).status_code == 401
    first = client.post("/api/auth/local/login", json={"credential": credential})
    assert first.status_code == 200
    old_token = client.cookies.get("omnix_session")
    second = client.post("/api/auth/local/login", json={"credential": credential})
    assert second.status_code == 200
    assert client.cookies.get("omnix_session") != old_token
    assert service.authenticate_session(old_token) is None
