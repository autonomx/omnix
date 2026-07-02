from __future__ import annotations

from app.assist_core.hermes_rpg_bridge_completion import hermes_rpg_active_integration_completion_payload


def test_hermes_rpg_active_integration_completion_payload_marks_current_range_ready() -> None:
    payload = hermes_rpg_active_integration_completion_payload()

    assert payload["ok"] is True
    assert payload["phases"] == list(range(201, 218))
    assert payload["active_integration_ready"] is True
