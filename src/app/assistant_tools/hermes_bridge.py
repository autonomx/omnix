"""Bridge helpers for Hermes assistant capability routes."""
from __future__ import annotations

from .calendar_adapter import run_calendar_tool_request
from .contacts_adapter import run_contacts_tool_request
from .gate import review_assistant_tool_request
from .gmail_adapter import run_gmail_tool_request
from .home_adapter import run_home_tool_request
from .hermes_payloads import HermesAssistantToolExecutePayload, HermesAssistantToolReviewPayload
from .kasa_adapter import run_kasa_tool_request
from .ledger import (
    AssistantToolLedgerEntry,
    append_assistant_tool_ledger_entry,
    assistant_tool_execution_for_proposal,
    summarize_tool_input,
)
from .models import AssistantToolRequest, AssistantToolResult, ToolRiskLevel
from .repo_adapter import run_repository_tool_request
from .result_context import tool_result_to_chat_context


def hermes_assistant_tool_review_payload(
    user_request: str,
    request: AssistantToolRequest,
) -> HermesAssistantToolReviewPayload:
    decision = review_assistant_tool_request(request)
    return HermesAssistantToolReviewPayload(
        user_request=user_request,
        selected_tool_id=request.tool_id,
        selected_action_id=request.action_id,
        tool_request=request,
        approval_decision=decision,
    )


def _run_assistant_tool_request(
    request: AssistantToolRequest,
    risk_level: ToolRiskLevel,
) -> AssistantToolResult:
    if request.tool_id == "gmail":
        result = run_gmail_tool_request(request)
        result.risk_level = risk_level
        return result
    if request.tool_id == "calendar":
        result = run_calendar_tool_request(request)
        result.risk_level = risk_level
        return result
    if request.tool_id == "contacts":
        result = run_contacts_tool_request(request)
        result.risk_level = risk_level
        return result
    if request.tool_id == "github":
        result = run_repository_tool_request(request)
        result.risk_level = risk_level
        return result
    if request.tool_id == "kasa":
        result = run_kasa_tool_request(request)
        result.risk_level = risk_level
        return result
    if request.tool_id == "home":
        result = run_home_tool_request(request)
        result.risk_level = risk_level
        return result
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        risk_level=risk_level,
        state_changed=False,
        result_summary="Assistant tool bridge accepted the governed request; runtime adapter dispatch is pending.",
        output={"adapter_status": "pending"},
    )


def hermes_assistant_tool_execute_payload(
    user_request: str,
    request: AssistantToolRequest,
) -> HermesAssistantToolExecutePayload:
    decision = review_assistant_tool_request(request)
    existing = assistant_tool_execution_for_proposal(request.proposal_id or "") if request.approved else None
    if existing is not None:
        result = AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level=decision.risk_level,
            state_changed=False,
            result_summary=f"This approved proposal was already executed as {existing.execution_id}.",
            output={"already_executed": True, "execution_id": existing.execution_id},
        )
        return HermesAssistantToolExecutePayload(
            user_request=user_request,
            selected_tool_id=request.tool_id,
            selected_action_id=request.action_id,
            approval_decision=decision,
            execution_result=result,
            result_context=tool_result_to_chat_context(result, existing),
            state_changed=False,
        )
    if decision.executable:
        result = _run_assistant_tool_request(request, decision.risk_level)
    else:
        result = AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level=decision.risk_level,
            state_changed=False,
            result_summary=decision.result_summary,
            error=decision.reason or "not_executable",
        )
    entry = append_assistant_tool_ledger_entry(
        AssistantToolLedgerEntry(
            session_id=request.session_id,
            proposal_id=request.proposal_id,
            tool_id=request.tool_id,
            action_id=request.action_id,
            approval_source="user" if request.approved else "policy",
            input_summary=summarize_tool_input(request.input),
            result_summary=result.result_summary,
            state_changed=result.state_changed,
            error=result.error,
        )
    )
    return HermesAssistantToolExecutePayload(
        user_request=user_request,
        selected_tool_id=request.tool_id,
        selected_action_id=request.action_id,
        approval_decision=decision,
        execution_result=result,
        result_context=tool_result_to_chat_context(result, entry),
        state_changed=result.state_changed,
    )
