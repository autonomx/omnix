from __future__ import annotations

from typing import Any, TypedDict

from .plan_risk_item import PlanRiskItem, normalize_plan_risk_item
from .plan_step_item import PlanStepItem, normalize_plan_step_item


class PlanResponse(TypedDict):
    ok: bool
    item_id: str
    summary: str
    review: bool
    executes: bool
    steps: list[PlanStepItem]
    risks: list[PlanRiskItem]


def plan_response_payload(payload: dict[str, Any]) -> PlanResponse:
    raw_steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    raw_risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    return {
        "ok": bool(payload.get("ok")),
        "item_id": str(payload.get("item_id") or "plan"),
        "summary": str(payload.get("summary") or "Review proposal before use."),
        "review": True,
        "executes": False,
        "steps": [normalize_plan_step_item(step) for step in raw_steps if isinstance(step, dict)],
        "risks": [normalize_plan_risk_item(risk) for risk in raw_risks if isinstance(risk, dict)],
    }
