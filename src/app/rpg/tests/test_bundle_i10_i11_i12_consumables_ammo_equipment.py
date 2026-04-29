from app.rpg.interactions.equipment_runtime import (
    ammo_compatible_with_equipped_weapon,
    consume_equipped_ammo,
    project_equipment_stats,
)
from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "hp": 10,
            "max_hp": 20,
            "inventory": {
                "items": [
                    {
                        "item_id": "item:minor_healing_potions",
                        "definition_id": "def:minor_healing_potion",
                        "name": "minor healing potion",
                        "aliases": ["healing potion", "potion"],
                        "quantity": 2,
                    },
                    {
                        "item_id": "item:hunting_bow",
                        "definition_id": "def:hunting_bow",
                        "name": "hunting bow",
                        "aliases": ["bow"],
                    },
                    {
                        "item_id": "item:iron_arrow_stack_a",
                        "definition_id": "def:iron_arrow",
                        "name": "iron arrows",
                        "aliases": ["arrows", "iron arrow"],
                        "quantity": 15,
                    },
                    {
                        "item_id": "item:padded_armor",
                        "definition_id": "def:padded_armor",
                        "name": "padded armor",
                        "aliases": ["armor"],
                    },
                ],
                "equipment": {},
                "carry_capacity": 50.0,
            },
        },
        "scene_items": [],
        "scene_objects": [],
    }


def _inventory(state):
    return state["player_state"]["inventory"]


def _item(state, item_id):
    for item in _inventory(state)["items"]:
        if item.get("item_id") == item_id:
            return item
    return {}


def test_consume_healing_potion_heals_and_decrements_quantity():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I drink the minor healing potion.",
        tick=1,
    )

    consumable = result["consumable_result"]
    assert consumable["resolved"] is True
    assert consumable["reason"] == "consumable_used"
    assert consumable["effect_result"]["hp_before"] == 10
    assert consumable["effect_result"]["hp_after"] == 15

    assert state["player_state"]["hp"] == 15
    assert _item(state, "item:minor_healing_potions")["quantity"] == 1


def test_equip_bow_arrows_and_armor_projects_stats():
    state = _state()

    bow = resolve_general_interaction(
        state,
        player_input="I equip the hunting bow.",
        tick=1,
    )
    assert bow["inventory_result"]["reason"] == "item_equipped"

    arrows = resolve_general_interaction(
        state,
        player_input="I equip the iron arrows as ammo.",
        tick=2,
    )
    assert arrows["inventory_result"]["reason"] == "ammo_equipped"

    armor = resolve_general_interaction(
        state,
        player_input="I equip the padded armor.",
        tick=3,
    )
    assert armor["inventory_result"]["reason"] == "item_equipped"

    equipment = _inventory(state)["equipment"]
    assert equipment["main_hand"] == "item:hunting_bow"
    assert equipment["ammo"] == "item:iron_arrow_stack_a"
    assert equipment["body"] == "item:padded_armor"

    stats = project_equipment_stats(state)["stats"]
    assert stats["damage_max"] >= 6
    assert stats["armor"] >= 1
    assert stats["accuracy_bonus"] >= 1


def test_ammo_compatibility_and_consumption():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I equip the hunting bow.",
        tick=1,
    )
    resolve_general_interaction(
        state,
        player_input="I equip the iron arrows as ammo.",
        tick=2,
    )

    compat = ammo_compatible_with_equipped_weapon(state)
    assert compat["compatible"] is True
    assert compat["reason"] == "ammo_compatible"

    consumed = consume_equipped_ammo(state, quantity=1, tick=3)
    assert consumed["consumed"] is True
    assert consumed["quantity_before"] == 15
    assert consumed["quantity_after"] == 14

    assert _item(state, "item:iron_arrow_stack_a")["quantity"] == 14


def test_consuming_last_ammo_clears_ammo_slot():
    state = _state()
    _item(state, "item:iron_arrow_stack_a")["quantity"] = 1

    resolve_general_interaction(
        state,
        player_input="I equip the hunting bow.",
        tick=1,
    )
    resolve_general_interaction(
        state,
        player_input="I equip the iron arrows as ammo.",
        tick=2,
    )

    consumed = consume_equipped_ammo(state, quantity=1, tick=3)
    assert consumed["consumed"] is True
    assert consumed["quantity_after"] == 0
    assert "ammo" not in _inventory(state)["equipment"]
