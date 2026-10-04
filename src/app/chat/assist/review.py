"""Assist mode review: risky calls wait for confirmation; pending confirmations and the action log."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.chat.assist.house import assist_data_root
from app.chat.assist.models import ActionLogEntry, ConfirmationRequest, AssistantResult, PolicyDecision, ToolCall, ToolRiskLevel


def pending_path() -> Path:
    return assist_data_root() / "pending_reviews.json"


def log_path() -> Path:
    return assist_data_root() / "action_log.jsonl"


def read_pending() -> dict[str, Any]:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().read_pending()
    path = pending_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_pending(data: dict[str, Any]) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().write_pending(data)
    pending_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def add_pending(item: ConfirmationRequest) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().add_pending(item)
    data = read_pending()
    data[item.confirmation_id] = asdict(item)
    write_pending(data)


def append_log(entry: ActionLogEntry) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().append_log(entry)
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")


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
