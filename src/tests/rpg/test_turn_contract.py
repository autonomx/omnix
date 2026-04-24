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
            }
        ],
        "scene_state": {"tension": 0},
    }


def test_attack_builds_interpreted_action_state_delta_and_brief():
    state = _state()
    contract = build_turn_contract(
        player_input="i punch bran in the face",
        action={"action_type": "attack_unarmed", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    assert contract["interpreted_action"]["intent"] == "attack"
    assert contract["interpreted_action"]["target_id"] == "bran"
    assert contract["state_delta"]["npc_updates"][0]["mood"] == "angry"
    assert "hostile" in contract["narration_brief"]["summary"].lower() or "attack" in contract["narration_brief"]["summary"].lower()
    assert contract["resolved_action"]["narrative_brief"]


def test_apply_state_delta_updates_npc_and_scene():
    state = _state()
    contract = build_turn_contract(
        player_input="i kick bran",
        action={"action_type": "attack_unarmed", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    updated = apply_state_delta(state, contract["state_delta"])
    bran = updated["actor_states"][0]

    assert bran["mood"] == "angry"
    assert bran["health"] < 100
    assert bran["relationship_to_player"] < 0
    assert updated["scene_state"]["tension"] > 0


def test_question_builds_narration_brief_without_fake_state_damage():
    state = _state()
    contract = build_turn_contract(
        player_input="i ask bran how business is lately",
        action={"action_type": "ask", "target_id": "bran"},
        resolved_action={"message": "You act."},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    assert contract["interpreted_action"]["intent"] == "ask"
    assert contract["state_delta"]["npc_updates"][0]["activity"] == "speaking with the player"
    assert "business" in contract["narration_brief"]["summary"].lower()