"""Role-based authorization (WP-4.3)."""
from __future__ import annotations

import re

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant
from app.security.auth import AGENT_RUNTIME_PATTERNS, PUBLIC_PATHS, PUBLIC_PREFIXES
from app.security.permissions import (
    CATALOG,
    DEFAULT_ROLE_PERMISSIONS,
    FEATURE_DEFAULTS,
    KERNEL_DEFAULTS,
    ROUTE_PERMISSIONS,
    WEBSOCKET_PERMISSIONS,
    ensure_permission,
    has_permission,
)
from tests.support.auth import FakeAuthenticator

# FastAPI's built-in documentation routes are protected by WP-4.10.
BUILT_IN_DOCS = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}


@pytest.fixture(scope="module")
def gateway():
    from app.composition.gateway.main import create_gateway_app

    authenticator = FakeAuthenticator()
    return create_gateway_app(auth_service=authenticator), authenticator


def _client(app, authenticator, roles):
    token, csrf = authenticator.issue_session(user_id="user:" + "-".join(roles), roles=roles)
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "test", "X-Omnix-CSRF": csrf},
        raise_server_exceptions=False,
    )
    client.cookies.set("omnix_session", token)
    return client


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def _public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def test_every_route_requires_a_permission_unless_public(gateway) -> None:
    """A signed-in caller with no permissions is refused everywhere."""
    app, authenticator = gateway
    client = _client(app, authenticator, ("nobody",))
    checked = 0
    for context in iter_route_contexts(app.router.routes):
        route = context.original_route
        path = context.path or route.path
        if _public(path) or path in BUILT_IN_DOCS:
            continue
        if "WebSocket" in type(route).__name__:
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(_concrete(path)):
                    pass
            assert closed.value.code == 1008, path
            checked += 1
            continue
        for method in sorted(getattr(route, "methods", None) or {"GET"}):
            if method == "HEAD":
                continue
            response = client.request(method, _concrete(path))
            if any(re.fullmatch(pattern, _concrete(path)) for pattern in AGENT_RUNTIME_PATTERNS):
                # Agent routes accept only run tokens, never a user session (WP-4.6).
                assert response.status_code == 401, (method, path, response.status_code)
                checked += 1
                continue
            assert response.status_code == 403, (method, path, response.status_code)
            assert response.json()["detail"]["error"] == "permission_denied"
            checked += 1
    assert checked > 300


def test_permission_tables_reference_the_catalog_and_real_routes(gateway) -> None:
    app, _ = gateway
    for pair in FEATURE_DEFAULTS.values():
        assert set(pair) <= set(CATALOG)
    for _, pair in KERNEL_DEFAULTS:
        assert pair is None or set(pair) <= set(CATALOG)
    assert set(WEBSOCKET_PERMISSIONS.values()) <= set(CATALOG)
    assert set(ROUTE_PERMISSIONS.values()) <= set(CATALOG)
    for permissions in DEFAULT_ROLE_PERMISSIONS.values():
        assert permissions <= set(CATALOG)
    routes = set()
    for context in iter_route_contexts(app.router.routes):
        route = context.original_route
        for method in getattr(route, "methods", None) or {"WS"}:
            routes.add((method, context.path or route.path))
    stale = [key for key in ROUTE_PERMISSIONS if key not in routes]
    assert not stale, f"ROUTE_PERMISSIONS entries without a route: {stale}"
    assert set(WEBSOCKET_PERMISSIONS) <= {path for _, path in routes}


@pytest.mark.parametrize(
    ("roles", "permission", "allowed"),
    [
        (("owner",), "workspace:transfer", True),
        (("admin",), "workspace:transfer", False),
        (("admin",), "trading:control", True),
        (("member",), "trading:paper:order", True),
        (("member",), "trading:control", False),
        (("member",), "tools:approve", False),
        (("member", "approver"), "tools:approve", True),
        (("approver",), "chat:write", False),
        (("viewer",), "chat:read", True),
        (("viewer",), "chat:write", False),
        (("viewer",), "settings:read", False),
        (("service",), "internal:service", True),
        (("system",), "jobs:read", False),
    ],
)
def test_role_matrix(roles, permission, allowed) -> None:
    assert has_permission(roles, permission) is allowed


def test_viewer_reads_but_cannot_mutate(gateway) -> None:
    app, authenticator = gateway
    viewer = _client(app, authenticator, ("viewer",))
    assert viewer.get("/api/jobs").status_code != 403
    denied = viewer.post("/api/jobs", json={})
    assert denied.status_code == 403
    assert denied.json()["detail"] == {"error": "permission_denied", "permission": "jobs:submit"}


def test_member_cannot_approve_tool_proposals_but_approver_can_reach_them(gateway) -> None:
    app, authenticator = gateway
    member = _client(app, authenticator, ("member",))
    path = "/api/assistant/tools/proposals/x/approve"
    assert member.post(path, json={}).status_code == 403
    approver = _client(app, authenticator, ("member", "approver"))
    assert approver.post(path, json={}).status_code != 403


def test_member_places_paper_orders_but_not_trading_controls(gateway) -> None:
    app, authenticator = gateway
    member = _client(app, authenticator, ("member",))
    assert member.post("/api/trading/paper/accounts/x/orders", json={}).status_code != 403
    assert member.post("/api/trading/paper/accounts/x/reset", json={}).status_code == 403


def test_agent_approval_commands_need_agent_approve() -> None:
    from fastapi import HTTPException

    member = TenantContext(user_id="u", workspace_id="w", membership_id="m", roles=frozenset({"member"}))
    token = push_tenant(member)
    try:
        ensure_permission("agent:steer")
        with pytest.raises(HTTPException) as denied:
            ensure_permission("agent:approve")
        assert denied.value.status_code == 403
    finally:
        pop_tenant(token)


def test_local_install_without_sign_in_keeps_full_access() -> None:
    from app.runtime.tenant_context import local_tenant_context

    for permission in CATALOG:
        if permission in {"internal:service"}:
            continue
        assert has_permission(local_tenant_context().roles, permission), permission


def test_permissions_document_is_current() -> None:
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "scripts/generate_permissions_doc.py"
    module = runpy.run_path(str(script))
    assert module["TARGET"].read_text(encoding="utf-8") == module["render"](), (
        "run scripts/generate_permissions_doc.py"
    )


def test_gateway_without_installed_tenant_serves_the_local_owner(monkeypatch) -> None:
    """Sign-in off and no persistence bootstrap (benchmarks): not a 500."""
    from app.composition.gateway.main import create_gateway_app
    from app.runtime import tenant_context

    class EmptyStore:
        def get_job(self, job_id):
            return None

    monkeypatch.setattr(tenant_context, "_PROCESS_DEFAULT", None)
    monkeypatch.delenv("OMNIX_AUTH_MODE", raising=False)
    app = create_gateway_app(job_store_factory=lambda: EmptyStore())
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    assert client.get("/api/jobs/missing").status_code == 404
