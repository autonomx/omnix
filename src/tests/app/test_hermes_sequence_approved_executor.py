from __future__ import annotations

from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core.hermes_rpg_execution_ledger import hermes_rpg_execution_ledger_recent, hermes_rpg_execution_ledger_reset
from app.assist_core.hermes_sequence_approved_executor import hermes_rpg_sequence_execute_step_payload


def sequence_state(*, status: str = "pending") -> dict:
    return {
        "ok": True,
        "session_id": "session-1",
        "sequence_id": "seq-1",
        "current_item_index": 0 if status != "done" else 1,
        "item_statuses": [{"item_index": 0, "item_id": "look", "status": status, "command_text": "look around"}],
        "sequence": {
            "sequence_id": "seq-1",
            "domain": "rpg",
            "state_owner": "rpg_sim",
            "items": [
                {"item_id": "look", "statement": "look around", "status": status},
                {"item_id": "listen", "statement": "listen carefully", "status": "pending"},
            ],
        },
    }


def test_sequence_execute_step_runs_one_item_through_approved_flow() -> None:
    hermes_rpg_execution_ledger_reset()
    written: list[dict] = []

    def submitter(payload: dict) -> dict:
        return {"ok": True, "turn": 8, "narration": f"Ran {payload['command_text']}", "state_changed": True}

    result = hermes_rpg_sequence_execute_step_payload(
        {"session_id": "session-1"},
        submitter=submitter,
        environ={FEATURE_FLAG: "1"},
        state_loader=lambda session_id: {"ok": True, "state": sequence_state()},
        state_writer=lambda state: written.append(state) or state,
    )

    assert result["ok"] is True
    assert result["status"] == "accepted"
    assert result["item_index"] == 0
    assert result["command_text"] == "look around"
    assert result["rpg_turn_result"]["turn"] == 8
    assert result["state_changed"] is True
    assert result["next_item_preview"]["item_id"] == "listen"
    assert written[0]["item_statuses"][0]["status"] == "done"
    assert hermes_rpg_execution_ledger_recent()["items"][0]["sequence_id"] == "seq-1"


def test_sequence_execute_step_stops_when_approved_flow_disabled() -> None:
    written: list[dict] = []

    result = hermes_rpg_sequence_execute_step_payload(
        {"session_id": "session-1"},
        submitter=lambda payload: {"ok": True},
        environ={},
        state_loader=lambda session_id: {"ok": True, "state": sequence_state()},
        state_writer=lambda state: written.append(state) or state,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["approved_flow"]["error"] == "hermes_rpg_approved_flow_disabled"
    assert result["sequence_state"]["status"] == "blocked"
    assert written[0]["item_statuses"][0]["status"] == "blocked"


def test_sequence_execute_step_reports_completed_sequence() -> None:
    state = sequence_state(status="done")
    state["current_item_index"] = 2

    result = hermes_rpg_sequence_execute_step_payload(
        {"session_id": "session-1"},
        state_loader=lambda session_id: {"ok": True, "state": state},
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["state_changed"] is False
    assert result["next_item_preview"] is None


def test_sequence_execute_step_requires_saved_state() -> None:
    result = hermes_rpg_sequence_execute_step_payload(
        {"session_id": "session-1"},
        state_loader=lambda session_id: {"ok": False, "state": None},
    )

    assert result == {
        "ok": False,
        "source": "hermes_sequence_approved_executor",
        "error": "sequence_state_not_found",
        "state_changed": False,
    }
