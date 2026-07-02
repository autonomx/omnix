from __future__ import annotations

from app.assist_core.hermes_rpg_flow_summary import hermes_rpg_flow_summary_payload


def test_hermes_rpg_flow_summary_lists_bridge_parts() -> None:
    payload = hermes_rpg_flow_summary_payload()

    assert payload["ok"] is True
    assert payload["parts"] == [
        "command_request",
        "request_guard",
        "ready_packet",
        "bridge_result",
        "flow_audit",
        "flow_error",
    ]
    assert payload["default_enabled"] is False
    assert payload["requires_user_step"] is True
    assert payload["state_changed"] is False
