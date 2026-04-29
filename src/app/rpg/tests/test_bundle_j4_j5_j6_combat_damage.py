import sys
import os
# Add src to path so app modules can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'src'))

from app.rpg.combat.runtime import resolve_combat_attack, start_combat_encounter


def _state():
    return {
        "session_id": "unit_combat_damage",
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "hp": 20,
            "max_hp": 20,
            "inventory": {
                "items": [
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "quantity": 15,
                    },
                ],
                "equipment": {
                    "main_hand": "item:hunting_bow",
                    "ammo": "item:iron_arrow_stack_a",
                },
                "carry_capacity": 50.0,
            },
            "party_state": {"companions": []},
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _force_player_turn(state):
    combat = state["combat_state"]
    for idx, row in enumerate(combat["initiative_order"]):
        if row["actor_id"] == "player":
            combat["turn_index"] = idx
            combat["current_actor_id"] = "player"
            state["combat_state"] = combat
            return


def test_combat_attack_applies_damage_and_consumes_ammo():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)
    _force_player_turn(state)

    before_ammo = next(
        item for item in state["player_state"]["inventory"]["items"]
        if item["item_id"] == "item:iron_arrow_stack_a"
    )["quantity"]

    result = resolve_combat_attack(
        state,
        actor_id="player",
        target_id="enemy:bandit_1",
        session_id="unit_combat_damage",
        tick=2,
    )

    assert result["resolved"] is True
    assert result["reason"] in {"combat_attack_resolved", "combat_defeat_resolved"}
    assert result["target_hp_after"] < result["target_hp_before"]
    assert result["damage_applied"] > 0

    after_ammo = next(
        item for item in state["player_state"]["inventory"]["items"]
        if item["item_id"] == "item:iron_arrow_stack_a"
    )["quantity"]
    assert after_ammo == before_ammo - 1


def test_combat_defeat_ends_combat_and_generates_loot():
    state = _state()
    start_combat_encounter(state, encounter_id="enc:bandit_ambush", tick=1)

    last = {}
    for tick in range(2, 10):
        _force_player_turn(state)
        last = resolve_combat_attack(
            state,
            actor_id="player",
            target_id="enemy:bandit_1",
            session_id="unit_combat_damage",
            tick=tick,
        )
        if last.get("combat_ended"):
            break

    assert last["reason"] == "combat_defeat_resolved"
    assert last["combat_ended"] is True
    assert state["combat_state"]["active"] is False
    assert last["loot_result"]["resolved"] is True