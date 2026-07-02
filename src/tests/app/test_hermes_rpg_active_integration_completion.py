from __future__ import annotations

from app.assist_core.hermes_rpg_bridge_completion import hermes_rpg_active_integration_completion_payload


def test_current_phase_range() -> None:
    payload = hermes_rpg_active_integration_completion_payload()

    assert payload["ok"] is True
    assert payload["phases"] == list(range(201, 221))
