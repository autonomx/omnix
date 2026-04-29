from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.item_model import (
    add_item_to_items_list,
    encumbrance_state_for_weight,
    normalize_item_instance,
    recalculate_inventory_derived_fields,
)


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "inventory": {
                "items": [],
                "equipment": {},
                "carry_capacity": 50.0,
            },
        },
        "scene_items": [
            {
                "item_id": "item:iron_arrow_stack_a",
                "definition_id": "def:iron_arrow",
                "name": "iron arrows",
                "aliases": ["arrows", "iron arrow"],
                "quantity": 5,
                "location_id": "loc_tavern_road",
            },
            {
                "item_id": "item:iron_arrow_stack_b",
                "definition_id": "def:iron_arrow",
                "name": "iron arrows",
                "aliases": ["arrows", "iron arrow"],
                "quantity": 10,
                "location_id": "loc_tavern_road",
            },
            {
                "item_id": "item:rusty_dagger",
                "definition_id": "def:rusty_dagger",
                "name": "rusty dagger",
                "aliases": ["dagger"],
                "location_id": "loc_tavern_road",
            },
            {
                "item_id": "item:heavy_anvil",
                "definition_id": "def:heavy_anvil",
                "name": "heavy anvil",
                "aliases": ["anvil"],
                "location_id": "loc_tavern_road",
            },
        ],
        "scene_objects": [],
    }


def _inventory(state):
    return state["player_state"]["inventory"]


def _item_by_def(state, definition_id):
    for item in _inventory(state)["items"]:
        if item.get("definition_id") == definition_id:
            return item
    return {}


def test_normalize_item_instance_from_definition():
    item = normalize_item_instance({
        "item_id": "item:rusty_dagger",
        "definition_id": "def:rusty_dagger",
    })

    assert item["name"] == "rusty dagger"
    assert item["kind"] == "weapon"
    assert item["quantity"] == 1
    assert item["unit_weight"] == 1.2
    assert item["total_weight"] == 1.2
    assert item["equipment"]["stats"]["damage_max"] == 4


def test_add_stackable_items_stacks_quantity():
    first = normalize_item_instance({
        "item_id": "item:iron_arrow_stack_a",
        "definition_id": "def:iron_arrow",
        "quantity": 5,
    })
    second = normalize_item_instance({
        "item_id": "item:iron_arrow_stack_b",
        "definition_id": "def:iron_arrow",
        "quantity": 10,
    })

    result = add_item_to_items_list([first], second)

    assert result["stacked"] is True
    assert result["items"][0]["quantity"] == 15
    assert result["items"][0]["total_weight"] == 0.75


def test_inventory_weight_and_encumbrance():
    inventory = recalculate_inventory_derived_fields({
        "carry_capacity": 10.0,
        "items": [
            {"definition_id": "def:iron_arrow", "quantity": 20},
            {"definition_id": "def:rusty_dagger"},
        ],
        "equipment": {},
    })

    assert inventory["carry_weight"] == 2.2
    assert inventory["encumbrance_state"] == "normal"

    assert encumbrance_state_for_weight(8, 10) == "burdened"
    assert encumbrance_state_for_weight(11, 10) == "overloaded"
    assert encumbrance_state_for_weight(16, 10) == "immobile"


def test_take_arrows_stacks_across_pickups():
    state = _state()

    first = resolve_general_interaction(
        state,
        player_input="I pick up 5 iron arrows.",
        tick=1,
    )
    assert first["inventory_result"]["reason"] == "item_added_to_inventory"

    second = resolve_general_interaction(
        state,
        player_input="I pick up 10 iron arrows.",
        tick=2,
    )
    assert second["inventory_result"]["stacked"] is True

    arrows = _item_by_def(state, "def:iron_arrow")
    assert arrows["quantity"] == 15
    assert arrows["total_weight"] == 0.75


def test_heavy_anvil_pushes_encumbrance_overloaded():
    state = _state()

    resolve_general_interaction(
        state,
        player_input="I pick up the heavy anvil.",
        tick=1,
    )

    inventory = _inventory(state)
    assert inventory["carry_weight"] == 65.0
    assert inventory["encumbrance_state"] in {"overloaded", "immobile"}
