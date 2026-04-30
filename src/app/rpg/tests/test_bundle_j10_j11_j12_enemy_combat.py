from app.rpg.combat.enemy_runtime import (
    choose_enemy_target,
    resolve_current_enemy_combat_turn,
)
from app.rpg.combat.runtime import get_combat_state


def _state():
    return {
        "session_id": "unit_enemy_combat",
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "hp": 3,
            "max_hp": 20,
            "inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0,
            },
            "party_state": {"companions": []},
        },
        "combat_state": {
            "active": True,
            "encounter_id": "enc:bandit_ambush",
            "round": 1,
            "turn_index": 0,
            "current_actor_id": "enemy:bandit_1",
            "initiative_order": [
                {"actor_id": "enemy:bandit_1", "initiative": 20, "roll": 20, "bonus": 0},
                {"actor_id": "player", "initiative": 1, "roll": 1, "bonus": 0},
            ],
            "participants": {
                "enemy:bandit_1": {
                    "actor_id": "enemy:bandit_1",
                    "side": "enemy",
                    "name": "Bandit",
                    "hp": 8,
                    "max_hp": 8,
                    "armor": 0,
                    "defense": 10,
                    "damage_min": 3,
                    "damage_max": 4,
                    "accuracy_bonus": 5,
                    "initiative_bonus": 0,
                    "status": "active",
                    "loot_table_id": "loot:bandit_common",
                },
                "player": {
                    "actor_id": "player",
                    "side": "party",
                    "name": "You",
                    "hp": 3,
                    "max_hp": 20,
                    "armor": 0,
                    "defense": 10,
                    "initiative_bonus": 0,
                    "status": "active",
                },
            },
            "combat_log": [],
        },
        "scene_items": [],
        "scene_objects": [],
    }


def test_enemy_selects_player_first():
    state = _state()

    target = choose_enemy_target(state, enemy_id="enemy:bandit_1")

    assert target["resolved"] is True
    assert target["target_id"] == "player"


def test_enemy_attack_can_defeat_party():
    state = _state()

    result = resolve_current_enemy_combat_turn(
        state,
        session_id="unit_enemy_combat",
        tick=1,
    )

    assert result["resolved"] is True
    assert result["reason"] == "party_defeat_resolved"
    assert result["party_defeated"] is True
    assert result["combat_ended"] is True

    combat = get_combat_state(state)
    assert combat["active"] is False
    assert combat["ended_reason"] == "party_side_defeated"
    assert state["player_state"]["hp"] == 0