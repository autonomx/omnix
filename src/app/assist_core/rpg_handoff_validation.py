from __future__ import annotations

from typing import Any

BLOCKED_HANDOFF_KEYS = frozenset({"state_delta", "inventory", "currency", "location"})


def validate_rpg_handoff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = sorted(key for key in BLOCKED_HANDOFF_KEYS if key in payload)
    has_marker = payload.get("simulation_must_validate") is True
    if blocked and not has_marker:
        return {
            "ok": False,
            "status": "simulation_validation_required",
            "blocked_keys": blocked,
            "review_required": True,
            "read_only": True,
            "executes": False,
        }
    return {
        "ok": bool(payload.get("command_text")),
        "status": "valid_for_review",
        "blocked_keys": blocked,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
