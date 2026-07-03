from fastapi.testclient import TestClient

from app.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    save_assistant_tools_config,
)
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload, hermes_assistant_tool_review_payload
from app.assistant_tools.models import AssistantToolRequest
from app.gateway.main import create_gateway_app


def _connected_config(tool_id: str) -> AssistantToolsConfigPayload:
    defaults = default_assistant_tools_config()
    return AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id=tool.tool_id,
                enabled=tool.tool_id == tool_id,
                connection_status="connected" if tool.tool_id == tool_id else "not_configured",
                actions=tool.actions,
            )
            for tool in defaults.tools
        ]
    )


def test_hermes_review_payload_records_request_selection_and_decision(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("contacts"), path)

    payload = hermes_assistant_tool_review_payload(
        "Find Ada's email",
        AssistantToolRequest(tool_id="contacts", action_id="contacts.search_contacts", session_id="chat:1"),
    )

    assert payload.user_request == "Find Ada's email"
    assert payload.selected_tool_id == "contacts"
    assert payload.selected_action_id == "contacts.search_contacts"
    assert payload.approval_decision.executable is True


def test_hermes_execute_payload_keeps_non_approved_write_from_running(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("gmail"), path)

    payload = hermes_assistant_tool_execute_payload(
        "Email Ada",
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email", session_id="chat:1"),
    )

    assert payload.approval_decision.approval_required is True
    assert payload.approval_decision.executable is False
    assert payload.execution_result.error == "approval_required"
    assert payload.state_changed is False


def test_hermes_execute_payload_records_approved_gmail_state_change(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("gmail"), path)

    payload = hermes_assistant_tool_execute_payload(
        "Draft Ada",
        AssistantToolRequest(
            tool_id="gmail",
            action_id="gmail.create_draft",
            session_id="chat:1",
            approved=True,
            input={"to": "ada@example.com", "subject": "Hello", "body": "Hi Ada"},
        ),
    )

    assert payload.approval_decision.executable is True
    assert payload.execution_result.error is None
    assert payload.execution_result.output["draft"]["to"] == "ada@example.com"
    assert payload.state_changed is True


def test_hermes_execute_payload_dispatches_calendar_adapter(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("calendar"), path)

    payload = hermes_assistant_tool_execute_payload(
        "Check my morning",
        AssistantToolRequest(
            tool_id="calendar",
            action_id="calendar.read_availability",
            session_id="chat:1",
            input={"start_time": "2026-07-03T08:30:00", "end_time": "2026-07-03T09:30:00"},
        ),
    )

    assert payload.approval_decision.executable is True
    assert payload.execution_result.error is None
    assert payload.execution_result.output["events"][0]["title"] == "Focus block"
    assert payload.state_changed is False


def test_hermes_execute_payload_dispatches_repository_adapter(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("github"), path)

    payload = hermes_assistant_tool_execute_payload(
        "Read repo status",
        AssistantToolRequest(
            tool_id="github",
            action_id="github.read_repo",
            session_id="chat:1",
            input={"repository": "autonomx/omnix"},
        ),
    )

    assert payload.approval_decision.executable is True
    assert payload.execution_result.error is None
    assert payload.execution_result.output["repository"] == "autonomx/omnix"
    assert payload.state_changed is False


def test_hermes_assistant_routes_are_separate_from_rpg_routes(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    save_assistant_tools_config(_connected_config("contacts"), path)
    client = TestClient(create_gateway_app())

    review = client.post(
        "/api/hermes/assistant/tools/review",
        json={"user_request": "Find Ada", "request": {"tool_id": "contacts", "action_id": "contacts.search_contacts"}},
    )
    executed = client.post(
        "/api/hermes/assistant/tools/execute",
        json={"user_request": "Find Ada", "request": {"tool_id": "contacts", "action_id": "contacts.search_contacts"}},
    )

    assert review.status_code == 200
    assert executed.status_code == 200
    assert review.json()["selected_tool_id"] == "contacts"
    assert executed.json()["execution_result"]["tool_id"] == "contacts"
