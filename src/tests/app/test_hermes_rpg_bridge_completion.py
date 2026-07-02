from __future__ import annotations

from app.assist_core.hermes_rpg_bridge_completion import hermes_rpg_bridge_completion_payload


def test_hermes_rpg_bridge_completion_lists_required_checks() -> None:
    payload = hermes_rpg_bridge_completion_payload()

    assert payload["ok"] is True
    assert payload["approved_bridge_complete"] is True
    assert payload["uses_canonical_submitter"] is True
    assert payload["default_enabled"] is False
    assert payload["checks"] == [
        "command_request",
        "request_guard",
        "ready_packet",
        "submit_bridge",
        "approved_flow",
        "flow_audit",
        "flow_error",
        "flow_summary",
    ]
