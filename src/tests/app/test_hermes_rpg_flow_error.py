from __future__ import annotations

from app.assist_core.hermes_rpg_flow_error import hermes_rpg_flow_error


def test_hermes_rpg_flow_error_reports_none_for_ok_flow() -> None:
    payload = hermes_rpg_flow_error({"ok": True, "state_changed": True})

    assert payload["ok"] is True
    assert payload["error"] == "none"
    assert payload["state_changed"] is True


def test_hermes_rpg_flow_error_reports_packet_not_ready() -> None:
    payload = hermes_rpg_flow_error({"ok": False, "packet": {"ready_for_rpg_pipeline": False}})

    assert payload["ok"] is False
    assert payload["error"] == "packet_not_ready"
    assert payload["state_changed"] is False
