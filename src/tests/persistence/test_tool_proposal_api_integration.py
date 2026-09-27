from __future__ import annotations

import os
import secrets
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_tools import proposals
from app.assistant_tools.config_store import default_assistant_tools_config
from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.models import AssistantToolResult
from app.assistant_tools.routes import register_assistant_tool_routes
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def client(monkeypatch):
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    assert urlsplit(url).path in {"/omnix_test", "/omnix_refactor_baseline"}
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=3))
    context = bootstrap_local_tenant(database)
    service = proposals.AssistantToolProposalService(database, context)
    config = default_assistant_tools_config()
    for tool in config.tools:
        tool.enabled = tool.tool_id == "gmail"
        tool.connection_status = "connected" if tool.enabled else "not_configured"
    monkeypatch.setattr(proposals, "review_assistant_tool_request", lambda request, **kwargs: review_assistant_tool_request(request, config=config, **kwargs))
    calls = []

    def execute(request, risk):
        calls.append(request)
        return AssistantToolResult(tool_id=request.tool_id, action_id=request.action_id, session_id=request.session_id, risk_level=risk, state_changed=True, result_summary="Sent.", output={"sent": True})

    monkeypatch.setattr(proposals, "_run_assistant_tool_request", execute)
    app = FastAPI()
    register_assistant_tool_routes(app)
    app.dependency_overrides[proposals.default_tool_proposal_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"}) as http:
            http.calls = calls
            http.database = database
            http.context = context
            http.config = config
            yield http
    finally:
        database.close()


def _request():
    return {"tool_id": "gmail", "action_id": "gmail.send_email", "session_id": "chat:test", "input": {"body": "Hello"}}


def _propose(client, request=None):
    response = client.post("/api/assistant/tools/proposals", json=request or _request())
    assert response.status_code == 200, response.text
    return response.json()["proposal_id"]


def _path(identifier, action):
    return f"/api/assistant/tools/proposals/{identifier}/{action}"


@pytest.mark.parametrize("field,value", [("approved", True), ("approval_policy", "allow_automatic")])
def test_public_envelope_rejects_client_approval_assertions(client, field, value):
    response = client.post("/api/assistant/tools/proposals", json={**_request(), field: value})
    assert response.status_code == 422
    assert client.calls == []


def test_propose_does_not_execute_and_execute_requires_approval(client):
    identifier = _propose(client)
    assert client.calls == []
    response = client.post(_path(identifier, "execute"))
    assert response.status_code == 403
    assert response.json()["detail"] == "approval_required"
    assert client.calls == []


def test_approve_then_execute_dispatches_once(client):
    identifier = _propose(client)
    approved = client.post(_path(identifier, "approve"), json={"reason": "Send this exact email"})
    assert approved.status_code == 200
    assert approved.json()["decision"] == "approved"
    result = client.post(_path(identifier, "execute"))
    assert result.status_code == 200
    assert result.json()["state_changed"] is True
    assert len(client.calls) == 1
    assert client.post(_path(identifier, "execute")).status_code == 409
    assert len(client.calls) == 1
    with client.database.connection() as connection:
        rows = connection.execute("SELECT payload FROM omnix_module_records WHERE workspace_id = %s AND module = 'assistant-tools' AND record_type = 'execution-ledger' AND payload->>'proposal_id' = %s", (client.context.workspace_id, identifier)).fetchall()
        assert len(rows) == 1
        assert rows[0][0]["error"] is None
        assert rows[0][0]["state_changed"] is True


def test_changed_input_cannot_use_an_approved_proposal(client):
    identifier = _propose(client)
    assert client.post(_path(identifier, "approve"), json={}).status_code == 200
    response = client.post(_path(identifier, "execute"), json={**_request(), "input": {"body": "Different"}})
    assert response.status_code == 409
    assert response.json()["detail"] == "proposal_digest_mismatch"
    assert client.calls == []


def test_denied_proposal_cannot_execute(client):
    identifier = _propose(client)
    assert client.post(_path(identifier, "deny"), json={}).json()["decision"] == "denied"
    assert client.post(_path(identifier, "execute")).status_code == 409
    assert client.calls == []


def test_expired_proposal_cannot_execute(client):
    identifier = _propose(client)
    assert client.post(_path(identifier, "approve"), json={}).status_code == 200
    with client.database.transaction() as connection:
        connection.execute("UPDATE omnix_capability_approvals SET created_at = CURRENT_TIMESTAMP - INTERVAL '1 day', expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = %s", (identifier,))
    assert client.post(_path(identifier, "execute")).status_code == 409
    assert client.calls == []


def test_operator_disabling_action_invalidates_pending_execution(client):
    identifier = _propose(client)
    assert client.post(_path(identifier, "approve"), json={}).status_code == 200
    next(tool for tool in client.config.tools if tool.tool_id == "gmail").enabled = False
    assert client.post(_path(identifier, "execute")).status_code == 403
    assert client.calls == []


def test_automatic_read_policy_executes_through_proposal_without_approval(client):
    identifier = _propose(client, {**_request(), "action_id": "gmail.read_email"})
    assert client.post(_path(identifier, "execute")).status_code == 200
    assert client.post(_path(identifier, "execute")).status_code == 409
    assert len(client.calls) == 1


def test_failure_is_redacted_and_consumed_proposal_remains_single_use(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("Traceback and sensitive provider details")

    monkeypatch.setattr(proposals, "_run_assistant_tool_request", fail)
    identifier = _propose(client)
    assert client.post(_path(identifier, "approve"), json={}).status_code == 200
    response = client.post(_path(identifier, "execute"))
    assert response.json()["execution_result"]["error"] == "tool_execution_failed"
    assert "Traceback" not in response.text
    assert "sensitive provider details" not in response.text
    assert client.post(_path(identifier, "execute")).status_code == 409


def test_internal_hermes_route_requires_token_and_same_durable_approval(client, monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    identifier = _propose(client)
    envelope = {"user_request": "Send", "request": {**_request(), "proposal_id": identifier}}
    path = "/api/hermes/assistant/tools/execute"
    assert client.post(path, json=envelope).status_code == 401
    headers = {"X-Omnix-Service-Token": token}
    assert client.post(path, json=envelope, headers=headers).status_code == 403
    assert client.post(_path(identifier, "approve"), json={}).status_code == 200
    assert client.post(path, json=envelope, headers=headers).status_code == 200
    assert client.post(path, json=envelope, headers=headers).status_code == 409
    assert len(client.calls) == 1


def test_internal_route_is_excluded_from_public_schema(client):
    schema = client.get("/openapi.json").json()
    assert "/api/hermes/assistant/tools/execute" not in schema["paths"]
    assert "/api/assistant/tools/proposals" in schema["paths"]
    properties = schema["components"]["schemas"]["AssistantToolRequest"]["properties"]
    assert "approved" not in properties
    assert "approval_policy" not in properties
