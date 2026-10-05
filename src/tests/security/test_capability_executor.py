"""A single capability executor; approvals bound to principals (WP-4.5)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.platform.assistant_tools import executor as tools_executor
from app.platform.assistant_tools.models import AssistantToolRequest
from app.capabilities import approvals
from app.capabilities.approvals import (
    ApproverNotAllowed,
    current_approver,
    require_self_approval_allowed,
)
from app.capabilities.executor import (
    CapabilityGrant,
    CapabilityRuntimeUnavailable,
    execute_capability,
)
from app.runtime import ports
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant

APP = Path(__file__).resolve().parents[2] / "app"


def _tenant(*roles: str, user: str = "user:alice") -> TenantContext:
    return TenantContext(user_id=user, workspace_id="workspace:w", membership_id="m", roles=frozenset(roles))


@pytest.fixture
def as_tenant():
    tokens = []

    def use(*roles: str, user: str = "user:alice"):
        tokens.append(push_tenant(_tenant(*roles, user=user)))

    yield use
    for token in reversed(tokens):
        pop_tenant(token)


def test_unknown_adapter_is_an_error_not_pending() -> None:
    result = tools_executor.run_capability_adapter(
        AssistantToolRequest(tool_id="nonexistent", action_id="nonexistent.do", session_id="s"), "low",
    )
    assert result.error == "unknown_adapter"
    assert result.output.get("adapter_status") is None


def test_execution_fails_closed_without_the_capability_runtime() -> None:
    ports.reset_port_bindings_for_tests()
    with pytest.raises(CapabilityRuntimeUnavailable):
        execute_capability(
            CapabilityGrant("chat", "session"),
            AssistantToolRequest(tool_id="kasa", action_id="kasa.get_state", session_id="s"),
        )


def test_execute_requires_a_grant() -> None:
    with pytest.raises(TypeError):
        execute_capability(True, AssistantToolRequest(tool_id="kasa", action_id="kasa.get_state"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "anyone", "subject_id": "s"},
        {"source": "chat", "subject_id": " "},
        {"source": "chat", "subject_id": "s", "approved_by": " "},
        {"source": "chat", "subject_id": "s", "policy_floor": "never"},
    ],
)
def test_grants_are_validated(kwargs) -> None:
    with pytest.raises(ValueError):
        CapabilityGrant(**kwargs)


def test_only_the_executor_dispatches_to_adapters() -> None:
    """Static check: adapter entry points and the runtime are referenced only by the executor."""
    adapter_functions = {function.__name__ for function in tools_executor.ADAPTERS.values()}
    owners = {APP / "platform" / "assistant_tools" / "executor.py"}
    offenders = []
    for path in APP.rglob("*.py"):
        if path in owners or path.name.endswith("_adapter.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        used = names & (adapter_functions | {"execute_with_grant", "hermes_assistant_tool_execute_payload"})
        if used:
            offenders.append((str(path.relative_to(APP)), sorted(used)))
    assert not offenders, offenders


def test_service_and_system_identities_never_approve(as_tenant) -> None:
    as_tenant("owner", "service")
    with pytest.raises(ApproverNotAllowed, match="approver_not_a_principal"):
        current_approver("tools:approve")
    as_tenant("system")
    with pytest.raises(ApproverNotAllowed):
        current_approver("agent:approve")


def test_approval_requires_the_permission(as_tenant) -> None:
    as_tenant("member")
    with pytest.raises(ApproverNotAllowed, match="permission_denied:tools:approve"):
        current_approver("tools:approve")
    as_tenant("member", "approver", user="user:bob")
    assert current_approver("tools:approve") == "user:bob"


def test_self_approval_without_sign_in_allows_every_risk(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_APPROVAL_SELF_ALLOWED_MAX_RISK", raising=False)
    monkeypatch.delenv("OMNIX_AUTH_MODE", raising=False)
    require_self_approval_allowed(requested_by="user:local", approver="user:local", risk_level="high")


def test_self_approval_ceiling(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_APPROVAL_SELF_ALLOWED_MAX_RISK", "low")
    require_self_approval_allowed(requested_by="user:a", approver="user:a", risk_level="low")
    with pytest.raises(ApproverNotAllowed, match="self_approval_not_allowed"):
        require_self_approval_allowed(requested_by="user:a", approver="user:a", risk_level="medium")
    # Another principal may approve above the ceiling.
    require_self_approval_allowed(requested_by="user:a", approver="user:b", risk_level="high")


def test_signed_in_installs_default_to_low_risk_self_approval(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_APPROVAL_SELF_ALLOWED_MAX_RISK", raising=False)
    monkeypatch.setenv("OMNIX_AUTH_MODE", "local")
    assert approvals.self_approval_max_risk() == "low"


def test_chat_confirmation_without_permission_is_not_an_approval(as_tenant) -> None:
    from app.platform.chat.live_agent_store import _confirmation_grant

    as_tenant("member")
    assert _confirmation_grant("chat:1").approved is False
    as_tenant("owner", user="user:owner")
    grant = _confirmation_grant("chat:1")
    assert grant.approved_by == "user:owner" and grant.source == "live_agent"


def test_agent_approval_commands_carry_the_approving_principal(monkeypatch, as_tenant) -> None:
    from fastapi import HTTPException

    from app.platform.agent_runtime import api

    sent = []

    class Service:
        def command(self, command):
            sent.append(command)
            return "snapshot"

    monkeypatch.setattr(api, "_service", lambda *_args: Service())
    forged = api.AgentCommandRequest(command_type="approve", payload={"approval_id": "a", "issued_by": "user:forged"})
    as_tenant("owner", user="user:owner")
    api.command_agent_run("run-1", forged, None)
    assert sent[0].payload == {"approval_id": "a", "issued_by": "user:owner"}

    steer = api.AgentCommandRequest(command_type="steer", payload={"message": "go", "issued_by": "user:forged"})
    api.command_agent_run("run-1", steer, None)
    assert "issued_by" not in sent[1].payload

    as_tenant("owner", "service", user="service:worker")
    with pytest.raises(HTTPException) as refused:
        api.command_agent_run("run-1", forged, None)
    assert refused.value.status_code == 403
    assert refused.value.detail == {"error": "approval_not_allowed", "reason": "approver_not_a_principal"}
