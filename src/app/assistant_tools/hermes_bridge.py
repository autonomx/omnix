"""Bridge helpers for Hermes assistant capability routes."""
from __future__ import annotations

from .gate import review_assistant_tool_request
from .hermes_payloads import HermesAssistantToolExecutePayload, HermesAssistantToolReviewPayload
from .models import AssistantToolRequest, AssistantToolResult


def hermes_assistant_tool_review_payload(user_request: str, request: AssistantToolRequest) -> HermesAssistantToolReviewPayload:
    decision = review_assistant_tool_request(request)
    return HermesAssistantToolReviewPayload(
        user_request=user_request,
        selected_tool_id=request.tool_id,
        selected_action_id=request.action_id,
        tool_request=request,
        approval_decision=decision,
    )


def hermes_assistant_tool_execute_payload(user_request: str, request: AssistantToolRequest) -> HermesAssistantToolExecutePayload:
    decision = review_assistant_tool_request(request)
    if decision.executable:
        result = AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level=decision.risk_level,
            state_changed=decision.state_changed,
            result_summary="Assistant tool bridge accepted the governed request; runtime adapter dispatch is pending.",
            output={"adapter_status": "pending"},
        )
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
    return HermesAssistantToolExecutePayload(
        user_request=user_request,
        selected_tool_id=request.tool_id,
        selected_action_id=request.action_id,
        approval_decision=decision,
        execution_result=result,
        state_changed=result.state_changed,
    )
