from __future__ import annotations

from app.assist_core.hermes_rpg_bridge_completion import (
    ACTIVE_INTEGRATION_CHECKS,
    hermes_rpg_active_integration_completion_payload,
)


def test_hermes_rpg_active_integration_completion_payload_marks_201_215_ready() -> None:
    payload = hermes_rpg_active_integration_completion_payload()

    assert payload["ok"] is True
    assert payload["source"] == "hermes_rpg_active_integration_completion"
    assert payload["phases"] == list(range(201, 216))
    assert payload["checks"] == list(ACTIVE_INTEGRATION_CHECKS)
    assert "approved_live_route_smoke" in payload["checks"]
    assert "approved_ui_config_awareness" in payload["checks"]
    assert "approved_ui_refresh_callback" in payload["checks"]
    assert "approved_real_session_e2e" in payload["checks"]
    assert "runtime_noncombat_intent_guard" in payload["checks"]
    assert "approved_turn_result_ux" in payload["checks"]
    assert "approved_execution_ledger" in payload["checks"]
    assert "approved_ledger_route" in payload["checks"]
    assert "hermes_sequence_contract" in payload["checks"]
    assert "hermes_sequence_validation" in payload["checks"]
    assert payload["active_integration_ready"] is True
    assert payload["approved_flow_available"] is True
    assert payload["simulation_owned"] is True
    assert payload["default_enabled"] is False
    assert payload["bridge"]["approved_bridge_complete"] is True
    assert payload["bridge"]["uses_canonical_submitter"] is True
