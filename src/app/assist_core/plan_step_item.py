from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

StepStatus = Literal["pending", "ready", "blocked"]


class PlanStepItem(TypedDict):
    id: str
    title: str
    description: str
    status: StepStatus
    reviewRequired: bool


def normalize_plan_step_item(payload: dict[str, Any]) -> PlanStepItem:
    status = str(payload.get("status") or "pending").lower()
    if status not in {"pending", "ready", "blocked"}:
        status = "pending"
    return {
        "id": str(payload.get("id") or "step"),
        "title": str(payload.get("title") or "Review step"),
        "description": str(payload.get("description") or "Review before use."),
        "status": cast(StepStatus, status),
        "reviewRequired": True,
    }
