from __future__ import annotations

from app.assist_core.hermes_sequence_planner_loop import hermes_sequence_planner_loop


def test_planner_loop_refines_duplicate_and_unsupported_items() -> None:
    result = hermes_sequence_planner_loop(
        {
            "sequence_id": "seq-1",
            "objective": "Plan",
            "domain": "rpg",
            "state_owner": "rpg_sim",
            "items": [
                {"item_id": "look", "statement": "look around", "user_gate": False},
                {"item_id": "look2", "statement": "look around", "user_gate": False},
                {"item_id": "spawn", "statement": "spawn gold", "user_gate": False},
            ],
        },
        {"current_location": "Pass"},
    )

    assert result["ok"] is True
    assert [item["item_id"] for item in result["sequence"]["items"]] == ["look"]
    assert {issue["kind"] for issue in result["critique_summary"]["issues"]} == {"likely_loop", "unsupported_action"}


def test_planner_loop_marks_risky_steps_for_review() -> None:
    result = hermes_sequence_planner_loop(
        {
            "sequence_id": "seq-1",
            "objective": "Plan",
            "domain": "rpg",
            "state_owner": "rpg_sim",
            "items": [{"item_id": "attack", "statement": "attack the bandit", "user_gate": False}],
        },
        {"current_location": "Pass"},
    )

    assert result["sequence"]["items"][0]["user_gate"] is True
    assert result["critique_summary"]["issues"][0]["detail"] == "combat_action"


def test_planner_loop_blocks_empty_invalid_plan() -> None:
    result = hermes_sequence_planner_loop({"items": []}, {})

    assert result["ok"] is False
    assert result["critique_summary"]["blocked"] is True
