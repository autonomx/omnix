from __future__ import annotations

from app.assist_core.hermes_rpg_bridge_completion import (
    ACTIVE_INTEGRATION_CHECKS,
    hermes_rpg_active_integration_completion_payload,
)


def test_hermes_rpg_active_integration_completion_payload_marks_201_210_ready() -> None:
    payload = hermes_rpg_active_integration_completion_payload()

    assert payload["ok"] is True
    assert payload["source"] == "hermes_rpg_active_integration_completion"
    assert payload["phases"] == list(range(201, 211))
    assert payload["checks"] == list(ACTIVE_INTEGRATION_CHECKS)
    assert payload["active_integration_ready"] is True
    assert payload["approved_flow_available"] is True
    assert payload["simulation_owned"] is True
    assert payload["default_enabled"] is False
    assert payload["bridge"]["approved_bridge_complete"] is True
    assert payload["bridge"]["uses_canonical_submitter"] is True
