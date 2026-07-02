from __future__ import annotations

from typing import Any


FLOW_PARTS = (
    "command_request",
    "request_guard",
    "ready_packet",
    "bridge_result",
    "flow_audit",
    "flow_error",
)


def hermes_rpg_flow_summary_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "source": "hermes_rpg_flow_summary",
        "parts": list(FLOW_PARTS),
        "default_enabled": False,
        "requires_user_step": True,
        "state_changed": False,
    }
