from app.rpg.combat.runtime import (
    advance_combat_turn,
    gate_combat_action,
    start_combat_encounter,
)
from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "hp": 20,
            "max_hp": 20,
            "inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0,
            },
            "party_state": {
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "identity_arc": "revenge_after_losing_tavern",
                        "inventory": {
                            "items": [],
                            "equipment": {},
                            "carry_capacity": 50.0,
                        },
                    }
                ]
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def test_start_combat_builds_participants_and_initiative():
    state = _state()

    result = start_combat_encounter(
        state,
        encounter_id="enc:bandit_ambush",
        tick=1,
    )

    assert result["resolved"] is True
    assert result["changed_state"] is True
    assert result["reason"] == "combat_started"

    combat = state["combat_state"]
    assert combat["active"] is True
    assert combat["round"] == 1
    assert combat["current_actor_id"]

    participants = combat["participants"]
    assert "player" in participants
    assert "npc:Bran" in participants
    assert "enemy:bandit_1" in participants

    assert len(combat["initiative_order"]) == 3


def test_combat_turn_gating_blocks_non_current_actor():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)

    current = state["combat_state"]["current_actor_id"]
    other = "player" if current != "player" else "npc:Bran"

    result = gate_combat_action(
        state,
        actor_id=other,
        action_kind="attack",
    )

    assert result["resolved"] is False
    assert result["reason"] == "not_actor_turn"
    assert result["current_actor_id"] == current


def test_advance_combat_turn_changes_current_actor():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)

    before = state["combat_state"]["current_actor_id"]

    result = advance_combat_turn(state, tick=2)

    assert result["resolved"] is True
    assert result["changed_state"] is True
    assert result["reason"] == "combat_turn_advanced"
    assert result["previous_actor_id"] == before
    assert result["current_actor_id"] != before


def test_attack_starts_combat_through_interaction_runtime():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I attack the bandit.",
        tick=1,
    )

    assert result["combat_result"]["resolved"] is True
    assert result["combat_result"]["reason"] == "combat_started"
    assert state["combat_state"]["active"] is True