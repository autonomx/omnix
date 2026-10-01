"""Audit logging for sensitive actions (WP-4.8)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant
from app.security import audit


class MemorySink:
    def __init__(self) -> None:
        self.events: list[audit.AuditEvent] = []

    def write(self, event: audit.AuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> list[tuple[str, str]]:
        return [(event.action, event.outcome) for event in self.events]


@pytest.fixture
def sink():
    memory = MemorySink()
    audit.install_audit_sink(memory)
    try:
        yield memory
    finally:
        audit.install_audit_sink(None)


@pytest.fixture
def tenant():
    tokens = []

    def use(*roles: str, user: str = "user:alice"):
        tokens.append(push_tenant(TenantContext(user_id=user, workspace_id="workspace:w", membership_id="m",
                                                roles=frozenset(roles))))

    yield use
    for token in reversed(tokens):
        pop_tenant(token)


def test_record_binds_principal_and_strips_content_and_secrets(sink, tenant) -> None:
    tenant("owner")
    audit.record("settings.update", target_type="setting", target_id="voice.default",
                 details={"prompt": "tell me a secret", "api_key": "sk-123", "nested": {"password": "x", "count": 2}})
    [event] = sink.events
    assert (event.actor_user_id, event.workspace_id) == ("user:alice", "workspace:w")
    assert event.details == {"prompt_chars": 16, "nested": {"count": 2}}


def test_unknown_actions_are_refused_and_no_sink_is_a_no_op() -> None:
    with pytest.raises(ValueError):
        audit.record("settings.whatever", target_type="x", target_id="y")
    audit.install_audit_sink(None)
    audit.record("settings.update", target_type="x", target_id="y")


def test_sink_failure_never_breaks_the_action(caplog) -> None:
    class Broken:
        def write(self, event):
            raise RuntimeError("database down")

    audit.install_audit_sink(Broken())
    try:
        audit.record("feature.toggle", target_type="feature", target_id="voice")
    finally:
        audit.install_audit_sink(None)
    assert "audit_write_failed" in caplog.text


def _connection(method: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(scope={"type": "http", "method": method, "path": path, "route": SimpleNamespace(path=path)})


async def _drive(guard_body, *, fail: Exception | None = None):
    generator = guard_body
    await generator.__anext__()
    if fail is None:
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()
    else:
        with pytest.raises(type(fail)):
            await generator.athrow(fail)


@pytest.mark.parametrize("permission,action", sorted(audit.PERMISSION_AUDIT_ACTIONS.items()))
def test_guarded_writes_are_audited_after_the_handler(sink, tenant, permission, action) -> None:
    from app.security.permissions import _authorized_and_audited

    tenant("owner")
    asyncio.run(_drive(_authorized_and_audited(_connection("POST", "/api/x"), permission)))
    asyncio.run(_drive(_authorized_and_audited(_connection("POST", "/api/x"), permission),
                       fail=HTTPException(status_code=409)))
    assert sink.actions() == [(action, "success"), (action, "failure")]
    assert sink.events[0].details == {"method": "POST", "permission": permission}


def test_denied_and_read_requests(sink, tenant) -> None:
    from app.security.permissions import _authorized_and_audited

    tenant("viewer")
    with pytest.raises(HTTPException):
        asyncio.run(_drive(_authorized_and_audited(_connection("POST", "/api/trading/x"), "trading:control")))
    assert sink.actions() == [("trading.control.update", "denied")]
    tenant("owner")
    asyncio.run(_drive(_authorized_and_audited(_connection("GET", "/api/trading/x"), "trading:read")))
    assert len(sink.events) == 1


def test_capability_execution_is_audited(sink, tenant, monkeypatch) -> None:
    from types import MappingProxyType

    from app.assistant_tools import executor
    from app.assistant_tools.models import AssistantToolRequest, AssistantToolResult

    tenant("owner")
    monkeypatch.setattr(executor, "ADAPTERS", MappingProxyType({
        "kasa": lambda request: AssistantToolResult(tool_id="kasa", action_id=request.action_id, state_changed=True),
    }))
    executor.run_capability_adapter(AssistantToolRequest(tool_id="kasa", action_id="kasa.turn_on"), "medium",
                                    source="agent_run")
    executor.run_capability_adapter(AssistantToolRequest(tool_id="nope", action_id="nope.x"), "low")
    assert sink.actions() == [("capability.execute", "success"), ("capability.execute", "failure")]
    assert sink.events[0].details["source"] == "agent_run"


def test_agent_run_commands_are_audited(sink, tenant, monkeypatch) -> None:
    from app.agent_runtime import api

    tenant("owner", user="user:owner")
    monkeypatch.setattr(api, "_service", lambda *_args: SimpleNamespace(command=lambda command: "snapshot"))
    api.command_agent_run("run-1", api.AgentCommandRequest(command_type="approve", payload={"approval_id": "a"}), None)
    api.command_agent_run("run-1", api.AgentCommandRequest(command_type="cancel"), None)
    api.command_agent_run("run-1", api.AgentCommandRequest(command_type="pause"), None)
    assert sink.actions() == [("approval.decide", "success"), ("agent.run.stop", "success")]
    assert sink.events[0].target_id == "a"


def test_chat_confirmations_are_audited(sink, tenant) -> None:
    from app.chat.live_agent_store import _confirmation_grant

    tenant("member")
    _confirmation_grant("chat:1")
    tenant("owner")
    _confirmation_grant("chat:1")
    assert sink.actions() == [("approval.decide", "denied"), ("approval.decide", "success")]


def test_postgres_sink_resolves_unknown_actors(monkeypatch) -> None:
    from app.persistence.audit import PostgresAuditSink

    statements = []

    class Connection:
        def execute(self, sql, params):
            statements.append(params)

    class Database:
        def transaction(self):
            from contextlib import contextmanager

            @contextmanager
            def scope():
                yield Connection()

            return scope()

    event = audit.AuditEvent(action="capability.execute", target_type="capability", target_id="kasa.turn_on",
                             outcome="success", workspace_id="workspace:w", actor_user_id="agent-run:1",
                             details={"source": "agent_run"})
    PostgresAuditSink(Database()).write(event)
    [params] = statements
    assert params[:5] == ("workspace:w", "agent-run:1", "capability", "kasa.turn_on", "capability.execute")
    assert '"actor":"agent-run:1"' in params[5] and '"outcome":"success"' in params[5]


def test_agent_run_start_is_audited(sink, tenant, monkeypatch) -> None:
    from app.agent_runtime import api

    tenant("owner")
    monkeypatch.setattr(api, "_service", lambda *_args: SimpleNamespace(
        submit_start=lambda spec, job_store: SimpleNamespace(run_id=spec.run_id),
    ))
    http_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime_services=SimpleNamespace(jobs=object()))))
    started = api.start_agent_run(
        api.StartAgentRunRequest(task="Summarize today's research notes", provider_id="lmstudio", model_id="m",
                                 profile="research"),
        http_request,
    )
    assert sink.actions() == [("agent.run.start", "success")]
    assert sink.events[0].target_id == started.run_id
    assert sink.events[0].details["profile"] == "research"
