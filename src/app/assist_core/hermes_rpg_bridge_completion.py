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

ACTIVE_INTEGRATION_CHECKS = (
    "canonical_submitter",
    "submit_adapter",
    "approved_flow_route",
    "fake_submitter_route_test",
    "ui_review_confirm",
    "flow_readout",
    "replay_determinism_fixture",
    "feature_flag_config",
    "approved_flow_happy_path",
    "active_integration_audit",
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


def hermes_rpg_active_integration_completion_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "source": "hermes_rpg_active_integration_completion",
        "phases": list(range(201, 211)),
        "checks": list(ACTIVE_INTEGRATION_CHECKS),
        "bridge": hermes_rpg_bridge_completion_payload(),
        "active_integration_ready": True,
        "approved_flow_available": True,
        "simulation_owned": True,
        "default_enabled": False,
    }
