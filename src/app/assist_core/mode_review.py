from __future__ import annotations

import uuid
from dataclasses import asdict

from .core import ActionLogEntry, AssistantResult, ConfirmationRequest, PolicyDecision, ToolCall, ToolRiskLevel
from .policy_store import add_pending, append_log


def review_call(call: ToolCall) -> PolicyDecision:
    risk = ToolRiskLevel(call.risk)
    if risk == ToolRiskLevel.LOW:
        return PolicyDecision(allowed=True, risk=risk, requires_confirmation=False, reason="low_risk")
    if risk == ToolRiskLevel.MEDIUM:
        return PolicyDecision(allowed=False, risk=risk, requires_confirmation=True, reason="medium_risk_review")
    return PolicyDecision(allowed=False, risk=risk, requires_confirmation=True, reason="high_risk_review")


def hold_for_review(result: AssistantResult, call: ToolCall, *, dry_run: bool) -> AssistantResult:
    token = str(uuid.uuid4())[:12]
    add_pending(ConfirmationRequest(confirmation_id=token, tool_call=call))
    append_log(
        ActionLogEntry(
            trace_id=token,
            action=call.name,
            domain=result.domain,
            dry_run=dry_run,
            success=False,
            detail={"review": True, "tool": call.name, "risk": str(call.risk)},
        )
    )
    result.success = True
    result.response = "I need confirmation before doing that."
    result.requires_confirmation = True
    result.confirmation_id = token
    result.tool_results = []
    return result


def policy_payload(decision: PolicyDecision) -> dict[str, object]:
    return asdict(decision)
