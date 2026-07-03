from fastapi.testclient import TestClient

from app.assistant_tools.capability_dashboard import build_assistant_capability_dashboard
from app.assistant_tools.config_store import AssistantToolConfigRecord, AssistantToolsConfigPayload, default_assistant_tools_config
from app.assistant_tools.ledger import AssistantToolLedgerEntry, AssistantToolLedgerPayload
from app.gateway.main import create_gateway_app


def _config_with_enabled(tool_id: str) -> AssistantToolsConfigPayload:
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


def test_capability_dashboard_counts_enabled_tools_and_recent_errors():
    dashboard = build_assistant_capability_dashboard(
        config=_config_with_enabled("gmail"),
        ledger=AssistantToolLedgerPayload(
            entries=[
                AssistantToolLedgerEntry(tool_id="gmail", action_id="gmail.read_email"),
                AssistantToolLedgerEntry(tool_id="gmail", action_id="gmail.send_email", error="approval_required"),
            ]
        ),
    )

    gmail = next(tool for tool in dashboard.tools if tool.tool_id == "gmail")
    assert dashboard.total_tools == 4
    assert dashboard.enabled_tools == 1
    assert dashboard.recent_execution_count == 2
    assert dashboard.recent_error_count == 1
    assert gmail.recent_error_count == 1


def test_capability_dashboard_route(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(tmp_path / "assistant_tools_config.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_LEDGER_PATH", str(tmp_path / "assistant_tools_ledger.jsonl"))
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/dashboard")

    assert response.status_code == 200
    assert response.json()["total_tools"] == 4
    assert {tool["tool_id"] for tool in response.json()["tools"]} == {"gmail", "calendar", "contacts", "github"}
