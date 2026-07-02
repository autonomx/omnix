from __future__ import annotations

from app.assist_core.hermes_rpg_flow_readout import hermes_rpg_flow_readout


def test_hermes_rpg_flow_readout_summarizes_accepted_flow() -> None:
    payload = hermes_rpg_flow_readout(
        {
            "ok": True,
            "packet": {
                "session_id": "s1",
                "context_hash": "abc",
                "command_text": "look",
                "ready_for_rpg_pipeline": True,
            },
            "result": {"ok": True},
            "state_changed": True,
        }
    )

    assert payload["ok"] is True
    assert payload["status"] == "accepted"
    assert payload["summary"] == "Hermes RPG command accepted"
    assert payload["error"] == "none"
    assert payload["state_changed"] is True
    assert payload["audit"]["rpg_ok"] is True


def test_hermes_rpg_flow_readout_summarizes_blocked_flow() -> None:
    payload = hermes_rpg_flow_readout(
        {
            "ok": False,
            "packet": {"ready_for_rpg_pipeline": False, "command_text": "look"},
            "result": {},
            "state_changed": False,
        }
    )

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert payload["summary"] == "Hermes RPG command blocked"
    assert payload["error"] == "packet_not_ready"
    assert payload["state_changed"] is False
