from app.assistant_tools.ledger import AssistantToolLedgerEntry
from app.assistant_tools.models import AssistantToolResult
from app.assistant_tools.result_context import tool_result_to_chat_context


def test_tool_result_context_includes_summary_and_ledger_reference():
    result = AssistantToolResult(
        tool_id="contacts",
        action_id="contacts.search_contacts",
        result_summary="Found 1 contact.",
        state_changed=False,
    )
    entry = AssistantToolLedgerEntry(
        execution_id="exec-1",
        tool_id="contacts",
        action_id="contacts.search_contacts",
    )

    context = tool_result_to_chat_context(result, entry)

    assert context.message == "Found 1 contact. Ledger: exec-1."
    assert context.ledger_ref == "exec-1"
    assert context.state_changed is False
    assert "summarized" in context.sensitive_summary


def test_tool_result_context_summarizes_errors():
    result = AssistantToolResult(
        tool_id="gmail",
        action_id="gmail.send_email",
        error="approval_required",
    )

    context = tool_result_to_chat_context(result)

    assert context.message == "Tool action gmail.send_email did not run: approval_required."
    assert context.ledger_ref is None
