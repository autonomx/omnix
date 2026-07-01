from __future__ import annotations

from typing import Any

from .omnix_mode_api_surface import omnix_mode_surfaces
from .result_display import result_display_payload


def route_decision_bridge_payload(result: dict[str, Any]) -> dict[str, Any]:
    plan_surface = next(
        surface for surface in omnix_mode_surfaces() if surface["path"] == "agent_plan"
    )
    return {
        "mode": "agent_mode",
        "route": plan_surface,
        "display": result_display_payload(result),
        "proposal_only": True,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
