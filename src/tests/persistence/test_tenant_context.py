from __future__ import annotations

import pytest

from app.persistence.tenant import TenantAccessDenied, TenantContext, local_tenant_context


def test_local_tenant_has_explicit_owner_membership() -> None:
    context = local_tenant_context()
    assert context.user_id == "user:local"
    assert context.workspace_id == "workspace:local"
    assert context.membership_id == "membership:local-owner"
    assert context.has_role("owner") is True


def test_tenant_context_rejects_empty_roles() -> None:
    with pytest.raises(ValueError, match="role"):
        TenantContext(
            user_id="user:test",
            workspace_id="workspace:test",
            membership_id="membership:test",
            roles=frozenset(),
        )


def test_tenant_context_enforces_workspace_and_role() -> None:
    context = TenantContext(
        user_id="user:test",
        workspace_id="workspace:a",
        membership_id="membership:test",
        roles=frozenset({"member"}),
    )
    with pytest.raises(TenantAccessDenied):
        context.require_workspace("workspace:b")
    with pytest.raises(TenantAccessDenied):
        context.require_role("admin")
