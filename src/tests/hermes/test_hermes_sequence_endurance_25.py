from __future__ import annotations

from app.apps.rpg.edge.hermes.approved_config import FEATURE_FLAG
from app.apps.rpg.edge.hermes.sequence_approved_executor import hermes_rpg_sequence_execute_step_payload
from app.apps.rpg.edge.hermes.sequence_checkpoint_policy import hermes_sequence_checkpoint_policy
from app.apps.rpg.edge.hermes.sequence_loop_guard import hermes_sequence_loop_guard
from app.apps.rpg.edge.hermes.sequence_state import build_hermes_sequence_state


def _safe_sequence_25() -> dict:
    verbs = ["inspect", "observe", "study", "scan", "note"]
    return {
        "sequence_id": "seq-25",
        "objective": "Survey the room without changing RPG state",
        "domain": "rpg",
        "state_owner": "rpg_sim",
        "risk": "low",
        "items": [
            {
                "item_id": f"item-{index + 1:02d}",
                "statement": f"{verbs[index % len(verbs)]} detail {index + 1:02d}",
                "status": "pending",
                "user_gate": False,
            }
            for index in range(25)
        ],
    }


def _ready_state(sequence: dict) -> dict:
    return build_hermes_sequence_state(
        session_id="session-25",
        review_payload={
            "ok": True,
            "sequence": sequence,
            "validation": {"ok": True, "errors": []},
            "gate": {"allowed": True, "blocked_count": 0},
            "checkpoint": {"requires_checkpoint": False, "reasons": []},
            "loop_guard": {"ok": True},
        },
    )


def _done_count(state: dict) -> int:
    return sum(item.get("status") in {"done", "completed"} for item in state.get("item_statuses", []))


def test_hermes_sequence_endurance_runs_25_steps_with_resume_progress() -> None:
    state = _ready_state(_safe_sequence_25())
    writes: list[dict] = []

    def load_state(session_id: str) -> dict:
        assert session_id == "session-25"
        return {"ok": True, "state": state}

    def write_state(updated: dict) -> dict:
        nonlocal state
        state = updated
        writes.append(updated)
        return updated

    def submitter(payload: dict) -> dict:
        return {
            "ok": True,
            "turn": len(writes) + 1,
            "narration": f"Observed {payload['command_text']}",
            "state_changed": True,
        }

    for expected_index in range(25):
        result = hermes_rpg_sequence_execute_step_payload(
            {"session_id": "session-25", "assist_mode": "auto_low_risk"},
            submitter=submitter,
            environ={FEATURE_FLAG: "1"},
            state_loader=load_state,
            state_writer=write_state,
        )

        assert result["ok"] is True
        assert result["status"] == "accepted"
        assert result["item_index"] == expected_index
        assert result["state_changed"] is True
        assert writes[-1]["current_item_index"] == expected_index + 1
        assert len(writes[-1]["sequence"]["items"]) == 25
        assert _done_count(writes[-1]) == expected_index + 1

    assert _done_count(state) == 25

    completed = hermes_rpg_sequence_execute_step_payload({"session_id": "session-25"}, state_loader=load_state)
    assert completed["ok"] is True
    assert completed["status"] == "completed"
    assert completed["next_item_preview"] is None


def test_hermes_sequence_endurance_guards_mixed_25_item_cases() -> None:
    sequence = _safe_sequence_25()
    sequence["items"][3]["statement"] = "buy a ration"
    sequence["items"][7]["statement"] = "wait"
    sequence["items"][11]["user_gate"] = True

    checkpoint = hermes_sequence_checkpoint_policy(sequence)
    assert "inventory_currency_change" in checkpoint["reasons"]
    assert "repeated_noop_command" in checkpoint["reasons"]

    duplicate = _safe_sequence_25()
    duplicate["items"][20]["statement"] = duplicate["items"][0]["statement"]
    assert hermes_sequence_loop_guard(duplicate)["stop_reason"] == "duplicate_command"

    repeated_id = _safe_sequence_25()
    repeated_id["items"][21]["item_id"] = repeated_id["items"][0]["item_id"]
    assert hermes_sequence_loop_guard(repeated_id)["stop_reason"] == "loop_detected"

    blocked_owner = _safe_sequence_25()
    blocked_owner["state_owner"] = "presentation"
    assert hermes_sequence_loop_guard(blocked_owner)["stop_reason"] == "state_mismatch"
