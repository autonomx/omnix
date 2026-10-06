
from app.platform.assistant_tools.config_store import (
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
)
from app.platform.assistant_tools.credentials import AssistantToolCredentialRecord
from app.platform.assistant_tools.gmail_adapter import FakeGmailRuntimeAdapter, GmailMessageRecord, GoogleGmailRuntimeAdapter, run_gmail_tool_request
from app.platform.assistant_tools.models import AssistantToolRequest


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

    monkeypatch.setattr("app.platform.assistant_tools.gmail_adapter._gmail_json", fake_gmail_json)
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




def test_without_a_connected_account_gmail_reports_missing_credentials(monkeypatch):
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_FAKE_GMAIL", raising=False)
    monkeypatch.setattr("app.platform.assistant_tools.gmail_adapter.credential_for_tool", lambda _tool: None)

    result = run_gmail_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email", input={"query": "receipt"}),
    )

    assert result.error == "missing_credentials"
    assert result.output == {"connection_status": "missing_credentials"}
    assert result.state_changed is False


def test_sample_gmail_data_needs_the_explicit_flag(monkeypatch):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_FAKE_GMAIL", "1")
    monkeypatch.setattr("app.platform.assistant_tools.gmail_adapter.credential_for_tool", lambda _tool: None)

    result = run_gmail_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.read_email", input={"query": ""}),
    )

    assert result.error is None
    assert result.output["messages"]


def _send(adapter, **values):
    return run_gmail_tool_request(
        AssistantToolRequest(tool_id="gmail", action_id="gmail.send_email", input=values), adapter,
    )


def test_an_approved_send_request_sends_through_the_adapter():
    adapter = FakeGmailRuntimeAdapter()

    result = _send(adapter, to="Ada <ada@example.com>, grace@example.org", subject="Notes", body="Attached.")

    assert result.error is None and result.state_changed is True and result.risk_level == "high"
    assert [sent.to for sent in adapter.sent] == ["ada@example.com, grace@example.org"]
    assert result.output["sent"]["id"] == adapter.sent[0].id


def test_a_draft_can_be_sent_by_id():
    adapter = FakeGmailRuntimeAdapter()
    draft = adapter.create_draft(to="ada@example.com", subject="Follow-up", body="Thanks")

    result = _send(adapter, draft_id=draft.id)

    assert result.error is None
    assert adapter.sent[0].subject == "Follow-up" and draft.id not in adapter.drafts


def test_invalid_recipients_are_refused_before_anything_is_sent():
    adapter = FakeGmailRuntimeAdapter()

    for to in ("", "example", "ada@localhost", ", ".join(f"user{index}@example.com" for index in range(21))):
        result = _send(adapter, to=to, subject="s", body="b")
        assert result.error == "gmail_send_invalid_recipients" and result.state_changed is False

    assert adapter.sent == []


def test_header_injection_in_the_subject_is_refused():
    adapter = GoogleGmailRuntimeAdapter(
        AssistantToolCredentialRecord(
            tool_id="gmail", provider="Google", access_token="access-token",
            account_email="ada@example.com", updated_at="2026-07-03T00:00:00+00:00",
        )
    )

    result = _send(adapter, to="ada@example.com", subject="Hi\r\nBcc: attacker@example.com", body="b")

    assert result.error and result.state_changed is False


def test_the_google_adapter_posts_messages_send_and_drafts_send(monkeypatch):
    import base64

    calls: list[tuple[str, dict]] = []

    def fake_gmail_json(method, url, access_token, body=None):
        calls.append((url, body))
        return {"id": "sent-1", "threadId": "thread-9"}

    monkeypatch.setattr("app.platform.assistant_tools.gmail_adapter._gmail_json", fake_gmail_json)
    adapter = GoogleGmailRuntimeAdapter(
        AssistantToolCredentialRecord(
            tool_id="gmail", provider="Google", access_token="access-token",
            account_email="ada@example.com", updated_at="2026-07-03T00:00:00+00:00",
        )
    )

    sent = adapter.send_message(to="ada@example.com", subject="Hello", body="Body text")
    adapter.send_message(to="", subject="", body="", draft_id="draft-7")

    assert sent.id == "sent-1" and sent.thread_id == "thread-9"
    assert calls[0][0].endswith("/users/me/messages/send")
    raw = base64.urlsafe_b64decode(calls[0][1]["raw"] + "==").decode()
    assert "To: ada@example.com" in raw and "Subject: Hello" in raw
    assert calls[1] == ("https://gmail.googleapis.com/gmail/v1/users/me/drafts/send", {"id": "draft-7"})
