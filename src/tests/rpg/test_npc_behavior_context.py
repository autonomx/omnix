from app.rpg.session.turn_contract import (
    apply_state_delta,
    build_turn_contract,
)


def _state():
    return {
        "actor_states": [
            {
                "id": "bran",
                "name": "Bran the Innkeeper",
                "mood": "neutral",
                "activity": "working the bar",
                "health": 100,
                "relationship_to_player": 0,
                "trust": 0,
                "fear": 0,
                "recent_memories": [],
            }
        ],
        "scene_state": {"tension": 0},
    }


def test_attack_creates_required_hostile_npc_reaction_context():
    state = _state()

    contract = build_turn_contract(
        player_input="i punch bran in the face",
        action={"action_type": "attack_unarmed", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    behavior = contract["npc_behavior_context"]

    assert behavior["target_id"] == "bran"
    assert behavior["required_reaction"] is True
    assert behavior["target_name"] == "Bran the Innkeeper"


def test_future_turn_sees_angry_bran_after_state_delta_applied():
    state = _state()

    attack_contract = build_turn_contract(
        player_input="i punch bran",
        action={"action_type": "attack_unarmed", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    updated_state = apply_state_delta(state, attack_contract["state_delta"])

    ask_contract = build_turn_contract(
        player_input="i ask bran how he feels",
        action={"action_type": "ask", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=updated_state,
        simulation_state_after=updated_state,
        runtime_state={},
    )

    behavior = ask_contract["npc_behavior_context"]

    assert behavior["mood"] == "angry"
    assert behavior["relationship_to_player"] < 0
    assert behavior["reaction_tone"] == "hostile"
    assert behavior["recent_memories"]