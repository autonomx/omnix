from __future__ import annotations

from typing import Any


BRIDGE_CHECKS = (
    "command_request",
    "request_guard",
    "ready_packet",
    "submit_bridge",
    "approved_flow",
    "flow_audit",
    "flow_error",
    "flow_summary",
)


def hermes_rpg_bridge_completion_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "source": "hermes_rpg_bridge_completion",
        "checks": list(BRIDGE_CHECKS),
        "approved_bridge_complete": True,
        "uses_canonical_submitter": True,
        "default_enabled": False,
    }
