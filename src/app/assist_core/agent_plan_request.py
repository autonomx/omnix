from __future__ import annotations

from typing import Any, TypedDict


class AgentPlanRequest(TypedDict):
    mode: str
    objective: str
    context: dict[str, Any]
    constraints: dict[str, bool]


def agent_plan_request_payload(objective: str, context: dict[str, Any] | None = None) -> AgentPlanRequest:
    return {
        "mode": "agent_mode",
        "objective": objective.strip(),
        "context": context or {},
        "constraints": {
            "no_execution": True,
            "requires_review": True,
        },
    }
