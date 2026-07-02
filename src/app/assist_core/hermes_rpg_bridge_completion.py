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
    "approved_route_config_gate",
    "approved_route_readout",
    "approved_live_route_smoke",
    "approved_ui_config_awareness",
    "approved_ui_refresh_callback",
    "approved_real_session_e2e",
    "runtime_noncombat_intent_guard",
    "approved_turn_result_ux",
    "approved_execution_ledger",
    "approved_ledger_route",
    "hermes_sequence_contract",
    "hermes_sequence_validation",
    "hermes_sequence_preview_ui",
    "hermes_sequence_preview_tests",
    "hermes_sequence_stepper",
    "hermes_sequence_stepper_tests",
    "hermes_sequence_gate",
    "hermes_sequence_gate_tests",
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
        "phases": list(range(201, 219)),
        "checks": list(ACTIVE_INTEGRATION_CHECKS),
        "bridge": hermes_rpg_bridge_completion_payload(),
        "active_integration_ready": True,
        "approved_flow_available": True,
        "simulation_owned": True,
        "default_enabled": False,
    }
