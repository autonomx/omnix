from __future__ import annotations

from typing import Any, Literal, TypedDict

RiskSeverity = Literal["low", "medium", "high"]


class PlanRiskItem(TypedDict):
    id: str
    label: str
    severity: RiskSeverity
    message: str
    reviewRequired: bool


def normalize_plan_risk_item(payload: dict[str, Any]) -> PlanRiskItem:
    severity = str(payload.get("severity") or "medium").lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"
    return {
        "id": str(payload.get("id") or "risk"),
        "label": str(payload.get("label") or "Review risk"),
        "severity": severity,  # type: ignore[typeddict-item]
        "message": str(payload.get("message") or "Review before use."),
        "reviewRequired": True,
    }
