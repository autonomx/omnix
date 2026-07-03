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
            "context": {"session_id": "s1", "context_hash": "sequence:seq-1:item-1:0", "checkpoint_reason": "combat_action"},
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
            "context_hash": "sequence:seq-1:item-1:0",
            "rpg_ok": True,
            "error": None,
        },
    )

    assert entry["execution_id"] == "hermes-rpg-1"
    assert entry["session_id"] == "s1"
    assert entry["context_hash"] == "sequence:seq-1:item-1:0"
    assert entry["command_text"] == "look around"
    assert entry["sequence_id"] == "seq-1"
    assert entry["item_id"] == "item-1"
    assert entry["approval_source"] == "approved_flow"
    assert entry["checkpoint_reason"] == "combat_action"
    assert entry["result_summary"] == "accepted"
    assert entry["readout_status"] == "accepted"
    assert entry["rpg_ok"] is True
    assert entry["state_changed"] is True
    assert entry["turn"] == 4
    assert entry["config_enabled"] is True

    recent = hermes_rpg_execution_ledger_recent()
    assert recent["ok"] is True
    assert recent["count"] == 1
    assert recent["items"] == [entry]


def test_hermes_rpg_execution_ledger_filters_by_session_and_sequence() -> None:
    hermes_rpg_execution_ledger_reset()
    for session_id, sequence_id in [("s1", "seq-1"), ("s2", "seq-2"), ("s1", "seq-3")]:
        hermes_rpg_execution_ledger_record(
            payload={"user_step": {"command_text": "look"}, "context": {"session_id": session_id, "context_hash": f"sequence:{sequence_id}:item-1:0"}},
            config={"enabled": True},
            flow={"ok": True, "state_changed": True, "result": {"rpg_result": {"turn": 1, "summary": sequence_id}}},
            readout={"status": "accepted", "session_id": session_id, "command_text": "look", "context_hash": f"sequence:{sequence_id}:item-1:0", "rpg_ok": True},
        )

    assert hermes_rpg_execution_ledger_recent(session_id="s1")["count"] == 2
    filtered = hermes_rpg_execution_ledger_recent(sequence_id="seq-2")
    assert filtered["count"] == 1
    assert filtered["items"][0]["session_id"] == "s2"
