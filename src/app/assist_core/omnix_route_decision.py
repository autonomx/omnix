from __future__ import annotations

from typing import Any

from .omnix_mode_policy import omnix_mode_policy
from .omnix_mode_router import omnix_mode_route


def omnix_route_decision_payload(mode: str | None = None) -> dict[str, Any]:
    selected_mode = (mode or "rpg").strip() or "rpg"
    try:
        route = omnix_mode_route(selected_mode)
        policy = omnix_mode_policy(selected_mode)
    except KeyError:
        return {"ok": False, "error": "unknown_mode", "mode": selected_mode, "source": "omnix_route_decision"}

    return {
        "ok": True,
        "source": "omnix_route_decision",
        "mode": route["mode"],
        "role": route["hermes_role"],
        "owner": route["execution_owner"],
        "review_required": route["requires_approval"],
        "capabilities": policy["hermes_capabilities"],
        "boundary": route["summary"],
    }
