from fastapi.testclient import TestClient

from app.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    save_assistant_tools_config,
)
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.ledger import (
    AssistantToolLedgerEntry,
    append_assistant_tool_ledger_entry,
    load_assistant_tool_ledger,
    summarize_tool_input,
)
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


def test_summarize_tool_input_is_stable_and_bounded():
    summary = summarize_tool_input({"z": "last", "a": "first", "long": "x" * 100, "n": 1, "extra": True})

    assert summary.startswith("a=first")
    assert "long=" in summary
    assert "+1 more" in summary
    assert len(summary) < 180


def test_ledger_append_and_load_returns_newest_first(tmp_path):
    path = tmp_path / "assistant_tools_ledger.jsonl"
    older = append_assistant_tool_ledger_entry(
        AssistantToolLedgerEntry(
            execution_id="old",
            tool_id="contacts",
            action_id="contacts.search_contacts",
            input_summary="q=Ada",
            result_summary="Found Ada.",
            created_at="2026-01-01T00:00:00+00:00",
        ),
        path,
    )
    newer = append_assistant_tool_ledger_entry(
        AssistantToolLedgerEntry(
            execution_id="new",
            tool_id="gmail",
            action_id="gmail.read_email",
            input_summary="from=Ada",
            result_summary="Found messages.",
            created_at="2026-01-02T00:00:00+00:00",
        ),
        path,
    )

    payload = load_assistant_tool_ledger(path)

    assert [entry.execution_id for entry in payload.entries] == [newer.execution_id, older.execution_id]


def test_hermes_execute_records_ledger_entry(monkeypatch, tmp_path):
    config_path = tmp_path / "assistant_tools_config.json"
    ledger_path = tmp_path / "assistant_tools_ledger.jsonl"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_LEDGER_PATH", str(ledger_path))
    save_assistant_tools_config(_connected_config("contacts"), config_path)

    payload = hermes_assistant_tool_execute_payload(
        "Find Ada",
        AssistantToolRequest(
            tool_id="contacts",
            action_id="contacts.search_contacts",
            session_id="chat:1",
            input={"q": "Ada"},
        ),
    )
    ledger = load_assistant_tool_ledger(ledger_path)

    assert payload.execution_result.error is None
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry.session_id == "chat:1"
    assert entry.tool_id == "contacts"
    assert entry.action_id == "contacts.search_contacts"
    assert entry.approval_source == "policy"
    assert entry.input_summary == "q=Ada"
    assert entry.error is None


def test_ledger_route_returns_persisted_entries(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_ledger.jsonl"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_LEDGER_PATH", str(path))
    append_assistant_tool_ledger_entry(
        AssistantToolLedgerEntry(
            execution_id="entry-1",
            tool_id="github",
            action_id="github.merge_pr",
            approval_source="user",
            input_summary="pr=1172",
            result_summary="Merge pending checks.",
            state_changed=False,
        ),
        path,
    )
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/ledger")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entries"][0]["execution_id"] == "entry-1"
    assert payload["entries"][0]["tool_id"] == "github"
    assert payload["entries"][0]["approval_source"] == "user"
