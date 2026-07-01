from __future__ import annotations

from typing import Any


def review_boundary_payload(decision: dict[str, Any], runner_available: bool = False) -> dict[str, Any]:
    accepted = decision.get("decision") == "approved"
    return {
        "ok": accepted,
        "decision": decision.get("decision", "pending"),
        "ready_for_execution": accepted and runner_available,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
