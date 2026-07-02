from __future__ import annotations

from app.assist_core.hermes_rpg_flow_audit import hermes_rpg_flow_audit


def test_hermes_rpg_flow_audit_records_packet_and_result() -> None:
    payload = hermes_rpg_flow_audit(
        {
            "ok": True,
            "packet": {"session_id": "s1", "context_hash": "abc", "command_text": "check inventory"},
            "result": {"ok": True},
            "state_changed": True,
        }
    )

    assert payload["ok"] is True
    assert payload["session_id"] == "s1"
    assert payload["context_hash"] == "abc"
    assert payload["command_text"] == "check inventory"
    assert payload["rpg_ok"] is True
    assert payload["state_changed"] is True
