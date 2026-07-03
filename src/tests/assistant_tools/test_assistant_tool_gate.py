from fastapi.testclient import TestClient

from app.assistant_tools import AssistantToolRequest, review_assistant_tool_request
from app.assistant_tools.config_store import (
    AssistantActionConfigRecord,
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    save_assistant_tools_config,
)
from app.gateway.main import create_gateway_app


def _connected_config(tool_id: str, *, enabled_actions: dict[str, bool] | None = None) -> AssistantToolsConfigPayload:
    payload = default_assistant_tools_config()
    enabled_actions = enabled_actions or {}
    tools = []
    for tool in payload.tools:
        actions = [
            AssistantActionConfigRecord(
                action_id=action.action_id,
                enabled=enabled_actions.get(action.action_id, action.enabled),
                approval_policy=action.approval_policy,
            )
            for action in tool.actions
        ]
        tools.append(
            AssistantToolConfigRecord(
                tool_id=tool.tool_id,
                enabled=tool.tool_id == tool_id,
                connection_status="connected" if tool.tool_id == tool_id else "not_configured",
                actions=actions,
            )
        )
    return AssistantToolsConfigPayload(tools=tools)


def test_contacts_read_can_run_automatically_when_connected():
    decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="contacts", action_id="contacts.search_contacts"),
        config=_connected_config("contacts"),
    )

    assert decision.allowed is True
    assert decision.executable is True
    assert decision.approval_required is False
    assert decision.state_changed is False


def test_gmail_send_requires_approval_before_execution():
    pending = review_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email"),
        config=_connected_config("gmail"),
    )
    approved = review_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email", approved=True),
        config=_connected_config("gmail"),
    )

    assert pending.allowed is True
    assert pending.executable is False
    assert pending.approval_required is True
    assert pending.reason == "approval_required"
    assert approved.allowed is True
    assert approved.executable is True


def test_gmail_delete_is_blocked_by_safe_default_action_config():
    decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.delete_email", approved=True),
        config=_connected_config("gmail"),
    )

    assert decision.allowed is False
    assert decision.executable is False
    assert decision.reason == "action_disabled"


def test_calendar_create_requires_approval_and_delete_is_blocked_by_default():
    create_decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="calendar", action_id="calendar.create_event"),
        config=_connected_config("calendar"),
    )
    delete_decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="calendar", action_id="calendar.delete_event", approved=True),
        config=_connected_config("calendar"),
    )

    assert create_decision.allowed is True
    assert create_decision.approval_required is True
    assert create_decision.executable is False
    assert delete_decision.allowed is False
    assert delete_decision.reason == "action_disabled"


def test_github_merge_requires_approval_when_connected():
    decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="github", action_id="github.merge_pr"),
        config=_connected_config("github"),
    )

    assert decision.allowed is True
    assert decision.approval_required is True
    assert decision.executable is False
    assert decision.risk_level == "high"


def test_missing_connection_blocks_even_enabled_read_action():
    payload = default_assistant_tools_config()
    gmail = next(tool for tool in payload.tools if tool.tool_id == "gmail")
    gmail.enabled = True
    gmail.connection_status = "not_configured"

    decision = review_assistant_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email"),
        config=payload,
    )

    assert decision.allowed is False
    assert decision.reason == "missing_connection"


def test_review_route_uses_persisted_config(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("contacts"), path)
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/assistant/tools/review",
        json={"tool_id": "contacts", "action_id": "contacts.search_contacts", "session_id": "chat:1", "input": {"q": "Ada"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["executable"] is True
    assert payload["approval_required"] is False
