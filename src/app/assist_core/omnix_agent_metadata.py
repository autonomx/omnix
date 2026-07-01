from __future__ import annotations

from typing import Any

from .omnix_mode_metadata import omnix_mode_metadata_payload


def omnix_agent_metadata_payload(objective: str | None = None) -> dict[str, Any]:
    route_payload = omnix_mode_metadata_payload("agent_mode")
    if not route_payload.get("ok"):
        return route_payload

    return {
        "ok": True,
        "source": "omnix_agent_metadata",
        "mode": "agent_mode",
        "objective": (objective or "").strip(),
        "route": route_payload["route"],
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
