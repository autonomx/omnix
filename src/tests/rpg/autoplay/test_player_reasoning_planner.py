from tests.rpg.autoplay.player_reasoning_planner import (
    deterministic_concrete_player_action,
    is_vague_player_action,
    normalize_player_reasoning_payload,
)


def test_vague_objective_action_detected():
    assert is_vague_player_action("I ask Bran if they know anything that can help with my current objective.")


def test_deterministic_concrete_action_for_witness_objective():
    context = {
        "active_objectives": [{"summary": "Find the witness"}],
        "nearby_npcs": [{"name": "Bran"}],
    }
    action = deterministic_concrete_player_action(context)
    assert "witness" in action.lower()
    assert "where" in action.lower() or "inspect" in action.lower()
    assert "current objective" not in action.lower()


def test_reasoning_payload_normalization_flags_vague_action():
    payload = normalize_player_reasoning_payload(
        {
            "best_next_action": "I ask Bran if they know anything that can help with my current objective."
        }
    )
    assert payload["is_vague"] is True