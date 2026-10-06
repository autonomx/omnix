from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.runtime.tenant_context import (
    TenantAccessDenied,
    TenantContext,
    current_tenant,
    install_process_tenant,
    local_tenant_context,
    reset_process_tenant_for_tests,
)
from app.security.auth import PRINCIPAL_STATE_KEY, AuthenticatedPrincipal
from app.security.request_tenant import RequestTenantMiddleware, current_principal


def _context(user: str, workspace: str) -> TenantContext:
    return TenantContext(user_id=user, workspace_id=workspace, membership_id=f"m:{user}:{workspace}", roles=frozenset({"member"}))


MEMBERSHIPS = {
    ("user:alice", "workspace:shared"): _context("user:alice", "workspace:shared"),
    ("user:local", "workspace:lab"): _context("user:local", "workspace:lab"),
}


def _resolver(user_id: str, workspace_id: str) -> TenantContext:
    try:
        return MEMBERSHIPS[(user_id, workspace_id)]
    except KeyError:
        raise TenantAccessDenied(f"{user_id} not in {workspace_id}") from None


class _PrincipalInjector:
    """Stands in for AuthenticationMiddleware."""

    def __init__(self, app, principal):
        self.app = app
        self.principal = principal

    async def __call__(self, scope, receive, send):
        if self.principal is not None and scope["type"] in {"http", "websocket"}:
            scope.setdefault("state", {})[PRINCIPAL_STATE_KEY] = self.principal
        await self.app(scope, receive, send)


def _app(principal=None) -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    def whoami() -> dict[str, str | None]:
        tenant = current_tenant()
        caller = current_principal()
        return {"user": tenant.user_id, "workspace": tenant.workspace_id, "principal": caller.user_id if caller else None}

    app.add_middleware(RequestTenantMiddleware, resolver=_resolver)
    app.add_middleware(_PrincipalInjector, principal=principal)
    return TestClient(app)


def setup_function() -> None:
    reset_process_tenant_for_tests()
    install_process_tenant(local_tenant_context())


def teardown_function() -> None:
    reset_process_tenant_for_tests()


def test_without_a_principal_the_local_tenant_stays_in_effect() -> None:
    assert _app().get("/whoami").json() == {"user": "user:local", "workspace": "workspace:local", "principal": None}


def test_local_user_may_select_another_of_their_workspaces() -> None:
    client = _app()
    assert client.get("/whoami", headers={"X-Omnix-Workspace": "workspace:lab"}).json()["workspace"] == "workspace:lab"
    assert client.get("/whoami", headers={"X-Omnix-Workspace": "workspace:other"}).status_code == 403


def test_principal_default_and_selected_workspaces() -> None:
    alice = AuthenticatedPrincipal(user_id="user:alice", context=_context("user:alice", "workspace:alice"), auth_method="session:oidc")
    client = _app(alice)
    assert client.get("/whoami").json() == {"user": "user:alice", "workspace": "workspace:alice", "principal": "user:alice"}
    shared = client.get("/whoami", headers={"X-Omnix-Workspace": "workspace:shared"})
    assert shared.json()["workspace"] == "workspace:shared"
    denied = client.get("/whoami", headers={"X-Omnix-Workspace": "workspace:local"})
    assert denied.status_code == 403
    assert denied.json() == {"detail": "workspace_access_denied"}


def test_ambiguous_workspace_headers_are_rejected() -> None:
    client = _app()
    response = client.get("/whoami", headers=[("X-Omnix-Workspace", "a"), ("X-Omnix-Workspace", "b")])
    assert response.status_code == 400
    assert client.get("/whoami", headers={"X-Omnix-Workspace": " "}).status_code == 400


def test_tenant_does_not_leak_between_requests() -> None:
    client = _app()
    assert client.get("/whoami", headers={"X-Omnix-Workspace": "workspace:lab"}).json()["workspace"] == "workspace:lab"
    assert client.get("/whoami").json()["workspace"] == "workspace:local"
