from __future__ import annotations

from typing import Any, TypedDict


class PlanResponse(TypedDict):
    ok: bool
    item_id: str
    summary: str
    steps: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    review: bool
    execute: bool


def plan_response_payload(
    item_id: str,
    summary: str,
    steps: list[dict[str, Any]] | None = None,
    risks: list[dict[str, Any]] | None = None,
) -> PlanResponse:
    return {
        "ok": True,
        "item_id": item_id.strip(),
        "summary": summary.strip(),
        "steps": steps or [],
        "risks": risks or [],
        "review": True,
        "execute": False,
    }
