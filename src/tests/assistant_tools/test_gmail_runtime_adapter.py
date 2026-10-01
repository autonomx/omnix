
from app.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
)
from app.assistant_tools.credentials import AssistantToolCredentialRecord
from app.assistant_tools.gmail_adapter import FakeGmailRuntimeAdapter, GmailMessageRecord, GoogleGmailRuntimeAdapter, run_gmail_tool_request
from app.assistant_tools.models import AssistantToolRequest


def _connected_gmail_config() -> AssistantToolsConfigPayload:
    defaults = default_assistant_tools_config()
    return AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id=tool.tool_id,
                enabled=tool.tool_id == "gmail",
                connection_status="connected" if tool.tool_id == "gmail" else "not_configured",
                actions=tool.actions,
            )
            for tool in defaults.tools
        ]
    )


def test_fake_gmail_adapter_searches_messages_and_updates_drafts():
    adapter = FakeGmailRuntimeAdapter(
        messages=[GmailMessageRecord(id="m1", sender="ada@example.com", subject="Receipt", snippet="Order receipt")]
    )

    messages = adapter.search_messages("receipt")
    draft = adapter.create_draft(to="ada@example.com", subject="Follow-up", body="Thanks")
    updated = adapter.update_draft(draft_id=draft.id, body="Thanks again")

    assert [message.id for message in messages] == ["m1"]
    assert updated.id == draft.id
    assert updated.body == "Thanks again"


def test_gmail_read_request_runs_through_runtime_adapter():
    adapter = FakeGmailRuntimeAdapter(
        messages=[GmailMessageRecord(id="m1", sender="ada@example.com", subject="Receipt", snippet="Order receipt")]
    )

    result = run_gmail_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email", input={"query": "receipt"}),
        adapter,
    )

    assert result.error is None
    assert result.state_changed is False
    assert result.result_summary == "Found 1 Gmail message."
    assert result.output["messages"][0]["id"] == "m1"


def test_connected_gmail_adapter_reads_messages_through_google_api(monkeypatch):
    calls: list[str] = []

    def fake_gmail_json(method, url, access_token, body=None):
        calls.append(url)
        assert access_token == "access-token"
        if url.startswith("https://gmail.googleapis.com/gmail/v1/users/me/messages?"):
            return {"messages": [{"id": "msg-1"}]}
        return {
            "id": "msg-1",
            "threadId": "thread-1",
            "snippet": "Hello from Gmail",
            "payload": {"headers": [{"name": "From", "value": "ada@example.com"}, {"name": "Subject", "value": "Hello"}]},
        }

    monkeypatch.setattr("app.assistant_tools.gmail_adapter._gmail_json", fake_gmail_json)
    adapter = GoogleGmailRuntimeAdapter(
        AssistantToolCredentialRecord(
            tool_id="gmail",
            provider="Google",
            access_token="access-token",
            account_email="ada@example.com",
            updated_at="2026-07-03T00:00:00+00:00",
        )
    )

    messages = adapter.search_messages("hello")

    assert calls
    assert messages == [GmailMessageRecord(id="msg-1", sender="ada@example.com", subject="Hello", snippet="Hello from Gmail", thread_id="thread-1")]


