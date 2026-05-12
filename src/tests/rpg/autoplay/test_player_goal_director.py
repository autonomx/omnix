from tests.rpg.autoplay.player_goal_director import (
    action_is_vague_objective,
    action_violates_goal_pressure,
    build_goal_pressure_context,
    deterministic_goal_pressure_action,
    format_goal_pressure_prompt,
)


def test_goal_pressure_activates_on_low_strict_progress_and_promotes_concrete_action():
    context = {
        "active_objectives": [{"objective_id": "obj:witness", "objective_text": "Find the witness"}],
        "quest_log_summary": {"active_count": 1, "completed_count": 0},
        "nearby_npcs": [{"name": "Bran"}],
        "suggested_actions": [
            {"command": "I listen to Bran for more details.", "category": "social", "priority": 80},
            {"command": "I follow the witness lead toward the road.", "category": "travel", "priority": 60},
        ],
    }
    pressure = build_goal_pressure_context(
        transcript=[{"player_action": "I listen to Bran."}] * 12,
        player_action_context=context,
        progress_quality_metrics={"turn_count": 30, "meaningful_progress_rate": 0.05, "no_change_turns": 20},
        turn_index=31,
    )

    assert pressure["active"] is True
    assert pressure["candidate_actions"][0]["command"] == "I follow the witness lead toward the road."
    assert "GOAL-PRESSURE DIRECTIVE" in format_goal_pressure_prompt(pressure)
    assert action_violates_goal_pressure("I listen to Bran for more elaboration.", pressure)
    assert deterministic_goal_pressure_action(pressure) == "I follow the witness lead toward the road."


def test_goal_pressure_repairs_vague_objective_action_to_concrete_witness_action():
    pressure = {
        "active": True,
        "active_objectives": [
            {"objective_text": "Find the witness near the tavern."}
        ],
        "target_counts": {"Bran": 3},
        "candidate_actions": [
            {"command": "I ask Bran if they know anything that can help with my current objective."}
        ],
    }

    assert action_is_vague_objective("I ask Bran if they know anything that can help with my current objective.")
    repaired = deterministic_goal_pressure_action(pressure)
    assert "where the witness was last seen" in repaired
    assert "current objective" not in repaired