from __future__ import annotations

from app.assist_core.hermes_rpg_execution_ledger import (
    hermes_rpg_execution_ledger_recent,
    hermes_rpg_execution_ledger_record,
    hermes_rpg_execution_ledger_reset,
)


def test_hermes_rpg_execution_ledger_records_latest_approved_result() -> None:
    hermes_rpg_execution_ledger_reset()

    entry = hermes_rpg_execution_ledger_record(
        payload={
            "user_step": {"command_text": "look around"},
            "context": {"session_id": "s1", "context_hash": "abc"},
        },
        config={"enabled": True},
        flow={
            "ok": True,
            "state_changed": True,
            "result": {"rpg_result": {"turn": 4}},
        },
        readout={
            "status": "accepted",
            "session_id": "s1",
            "command_text": "look around",
            "context_hash": "abc",
            "rpg_ok": True,
            "error": None,
        },
    )

    assert entry["execution_id"] == "hermes-rpg-1"
    assert entry["session_id"] == "s1"
    assert entry["context_hash"] == "abc"
    assert entry["command_text"] == "look around"
    assert entry["readout_status"] == "accepted"
    assert entry["rpg_ok"] is True
    assert entry["state_changed"] is True
    assert entry["turn"] == 4
    assert entry["config_enabled"] is True

    recent = hermes_rpg_execution_ledger_recent()
    assert recent["ok"] is True
    assert recent["count"] == 1
    assert recent["items"] == [entry]
