from fastapi.testclient import TestClient

from app.assistant_tools import assistant_tool_registry_payload, default_assistant_tools
from app.gateway.main import create_gateway_app

EXPECTED_TOOLS = {"gmail", "calendar", "contacts", "github"}
EXPECTED_ACTIONS = {
    "gmail.read_email",
    "gmail.create_draft",
    "gmail.send_email",
    "calendar.read_availability",
    "calendar.create_event",
    "contacts.search_contacts",
    "github.read_repo",
    "github.create_branch",
    "github.create_pr",
    "github.merge_pr",
}


def test_backend_registry_exposes_expected_chat_tools_and_actions():
    payload = assistant_tool_registry_payload(default_assistant_tools())

    assert {tool.id for tool in payload.tools} == EXPECTED_TOOLS
    assert EXPECTED_ACTIONS <= {action.id for action in payload.actions}
    for tool in payload.tools:
        assert tool.enabled is False
        assert tool.connection_status == "not_configured"
        for action in tool.actions:
            assert action.tool_id == tool.id
            assert action.id.startswith(f"{tool.id}.")


def test_backend_registry_safe_defaults_match_tool_risk():
    payload = assistant_tool_registry_payload()
    actions = {action.id: action for action in payload.actions}

    assert actions["gmail.read_email"].approval_policy == "allow_automatic"
    assert actions["calendar.read_availability"].approval_policy == "allow_automatic"
    assert actions["contacts.search_contacts"].approval_policy == "allow_automatic"
    assert actions["gmail.create_draft"].approval_policy == "ask_sensitive"
    assert actions["calendar.create_event"].approval_policy == "always_ask"
    assert actions["github.merge_pr"].approval_policy == "always_ask"


def test_assistant_tools_route_returns_backend_registry():
    client = TestClient(create_gateway_app())
    response = client.get("/api/assistant/tools")

    assert response.status_code == 200
    payload = response.json()
    assert {tool["id"] for tool in payload["tools"]} == EXPECTED_TOOLS
    assert EXPECTED_ACTIONS <= {action["id"] for action in payload["actions"]}
