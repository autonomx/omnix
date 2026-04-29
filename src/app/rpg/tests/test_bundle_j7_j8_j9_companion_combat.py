import sys
import os
# Add src to path so app modules can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'src'))

from app.rpg.combat.companion_runtime import (
    choose_companion_combat_tactic,
    companion_morale_state,
    resolve_companion_combat_turn,
)
from app.rpg.combat.runtime import start_combat_encounter


def _state():
    return {
        "session_id": "unit_companion_combat",
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
                        "current_role": "Displaced tavern keeper",
                        "identity_arc": "revenge_after_losing_tavern",
                        "active_motivations": ["revenge"],
                        "loyalty": 35,
                        "inventory": {
                            "items": [
                                {
                                    "item_id": "item:bran_rusty_dagger",
                                    "definition_id": "def:rusty_dagger",
                                    "name": "rusty dagger",
                                }
                            ],
                            "equipment": {
                                "main_hand": "item:bran_rusty_dagger",
                            },
                            "carry_capacity": 50.0,
                        },
                    }
                ]
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _force_bran_turn(state):
    combat = state["combat_state"]
    for idx, row in enumerate(combat["initiative_order"]):
        if row["actor_id"] == "npc:Bran":
            combat["turn_index"] = idx
            combat["current_actor_id"] = "npc:Bran"
            state["combat_state"] = combat
            return


def test_bran_revenge_arc_sets_motivated_morale():
    state = _state()
    bran = state["player_state"]["party_state"]["companions"][0]

    morale = companion_morale_state(bran)

    assert morale["morale_state"] == "motivated"
    assert morale["accuracy_bonus"] >= 1


def test_companion_tactic_targets_living_enemy():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)

    tactic = choose_companion_combat_tactic(state, npc_id="npc:Bran")

    assert tactic["resolved"] is True
    assert tactic["target_id"] == "enemy:bandit_1"
    assert tactic["tactic"] == "revenge_attack"


def test_companion_combat_turn_resolves_attack():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)
    _force_bran_turn(state)

    result = resolve_companion_combat_turn(
        state,
        npc_id="npc:Bran",
        session_id="unit_companion_combat",
        tick=2,
    )

    assert result["resolved"] is True
    assert result["reason"] in {
        "companion_combat_attack_resolved",
        "companion_combat_defeat_resolved",
    }
    assert result["actor_id"] == "npc:Bran"
    assert result["target_id"] == "enemy:bandit_1"
    assert result["morale"]["morale_state"] == "motivated"

    attack = result["attack_result"]
    assert attack["morale_accuracy_bonus"] == 1
    assert attack["morale_damage_bonus"] == 1
    assert attack["attack_total"] == (
        attack["attack_roll"]
        + attack["equipment_accuracy_bonus"]
        + attack["morale_accuracy_bonus"]
    )
    if attack["hit"]:
        assert attack["damage_applied"] == max(
            1,
            attack["damage_roll"]
            + attack["morale_damage_bonus"]
            - attack["armor_reduction"],
        )