from fastapi.testclient import TestClient

from app.assistant_tools.config_store import (
    AssistantActionConfigRecord,
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    load_assistant_tools_config,
    save_assistant_tools_config,
)
from app.gateway.main import create_gateway_app


def test_default_config_uses_safe_approval_policies():
    payload = default_assistant_tools_config()
    actions = {action.action_id: action for tool in payload.tools for action in tool.actions}

    assert actions["gmail.read_email"].enabled is True
    assert actions["gmail.read_email"].approval_policy == "allow_automatic"
    assert actions["gmail.create_draft"].approval_policy == "ask_sensitive"
    assert actions["gmail.send_email"].approval_policy == "always_ask"
    assert actions["gmail.delete_email"].enabled is False
    assert actions["calendar.delete_event"].enabled is False


def test_config_save_and_load_preserves_known_tool_settings(tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    request = AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id="gmail",
                enabled=True,
                connection_status="connected",
                actions=[
                    AssistantActionConfigRecord(action_id="gmail.read_email", enabled=True, approval_policy="allow_automatic"),
                    AssistantActionConfigRecord(action_id="gmail.send_email", enabled=True, approval_policy="always_ask"),
                ],
            )
        ]
    )

    saved = save_assistant_tools_config(request, path)
    loaded = load_assistant_tools_config(path)
    gmail = next(tool for tool in loaded.tools if tool.tool_id == "gmail")
    gmail_actions = {action.action_id: action for action in gmail.actions}

    assert saved == loaded
    assert gmail.enabled is True
    assert gmail.connection_status == "connected"
    assert gmail_actions["gmail.send_email"].enabled is True
    assert "calendar" in {tool.tool_id for tool in loaded.tools}


def test_assistant_tool_config_routes_persist_payload(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    client = TestClient(create_gateway_app())

    initial = client.get("/api/assistant/tools/config")
    assert initial.status_code == 200
    payload = initial.json()
    gmail = next(tool for tool in payload["tools"] if tool["tool_id"] == "gmail")
    gmail["enabled"] = True
    gmail["connection_status"] = "connected"

    saved = client.post("/api/assistant/tools/config", json=payload)
    loaded = client.get("/api/assistant/tools/config")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    saved_gmail = next(tool for tool in loaded.json()["tools"] if tool["tool_id"] == "gmail")
    assert saved_gmail["enabled"] is True
    assert saved_gmail["connection_status"] == "connected"
