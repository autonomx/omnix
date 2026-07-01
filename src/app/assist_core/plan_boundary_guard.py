from __future__ import annotations

from typing import Any

BLOCKED_KEYS = frozenset({"state_delta", "inventory", "currency", "location"})


def plan_boundary_guard(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = sorted(key for key in BLOCKED_KEYS if key in payload)
    if blocked:
        return {
            "ok": False,
            "status": "blocked_by_boundary",
            "blocked_keys": blocked,
            "simulation_must_validate": True,
            "review_required": True,
            "read_only": True,
            "executes": False,
        }
    return {
        "ok": True,
        "status": "allowed_for_review",
        "blocked_keys": [],
        "simulation_must_validate": True,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
