from __future__ import annotations

from app.assist_core.hermes_sequence_stepper import hermes_sequence_step_once


def sequence_fixture(first_status: str = "ready") -> dict:
    return {
        "sequence_id": "seq-1",
        "objective": "Review current location",
        "domain": "rpg",
        "state_owner": "rpg_sim",
        "items": [
            {"item_id": "look", "statement": "look around", "status": first_status, "user_gate": False},
            {"item_id": "local", "statement": "local update", "status": "pending", "user_gate": True},
        ],
    }


def test_hermes_sequence_step_once_advances_first_ready_item() -> None:
    seen: list[dict] = []

    def handler(payload: dict) -> dict:
        seen.append(payload)
        return {"ok": True}

    result = hermes_sequence_step_once(sequence_fixture(), handler)

    assert result["ok"] is True
    assert result["status"] == "advanced"
    assert result["item_index"] == 0
    assert result["item"]["status"] == "done"
    assert seen[0]["statement"] == "look around"


def test_hermes_sequence_step_once_pauses_for_review_gate() -> None:
    result = hermes_sequence_step_once(sequence_fixture(first_status="done"), lambda payload: {"ok": True})

    assert result["ok"] is False
    assert result["status"] == "needs_review"
    assert result["item_index"] == 1
    assert result["state_changed"] is False


def test_hermes_sequence_step_once_blocks_invalid_sequence() -> None:
    result = hermes_sequence_step_once({"items": []}, lambda payload: {"ok": True})

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "missing_objective" in result["errors"]
    assert "missing_items" in result["errors"]


def test_hermes_sequence_step_once_reports_complete_sequence() -> None:
    sequence = sequence_fixture(first_status="done")
    sequence["items"][1]["status"] = "done"

    result = hermes_sequence_step_once(sequence, lambda payload: {"ok": True})

    assert result["ok"] is True
    assert result["status"] == "complete"
    assert result["state_changed"] is False
