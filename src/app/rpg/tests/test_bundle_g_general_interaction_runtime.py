from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.semantic_actions import resolve_semantic_action_v2
from app.rpg.interactions.target_resolver import resolve_target_ref


def _state():
    return {
        "location_id": "loc_tavern_road",
        "player_state": {
            "location_id": "loc_tavern_road",
            "party_state": {
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "status": "active",
                        "location_id": "loc_tavern_road",
                    }
                ]
            },
            "inventory": {
                "items": [
                    {
                        "item_id": "item:small_knife",
                        "name": "small knife",
                        "aliases": ["knife"],
                    }
                ]
            },
        },
        "scene_objects": [
            {
                "object_id": "obj:broken_cart",
                "name": "broken cart",
                "aliases": ["cart", "wagon"],
                "location_id": "loc_tavern_road",
            },
            {
                "object_id": "obj:locked_chest",
                "name": "locked chest",
                "aliases": ["chest"],
                "location_id": "loc_tavern_road",
            },
        ],
        "scene_items": [
            {
                "item_id": "item:rusty_key",
                "name": "rusty key",
                "aliases": ["key"],
                "location_id": "loc_tavern_road",
            },
            {
                "item_id": "item:rope",
                "name": "rope",
                "aliases": ["length of rope"],
                "location_id": "loc_tavern_road",
            },
        ],
    }


def test_semantic_action_resolver_inspect():
    action = resolve_semantic_action_v2(player_input="I inspect the broken cart.")

    assert action["resolved"] is True
    assert action["kind"] == "inspect"
    assert action["target_ref"] == "broken cart"


def test_target_resolver_finds_scene_object_alias():
    result = resolve_target_ref(
        _state(),
        target_ref="cart",
        expected_types=["object"],
    )

    assert result["resolved"] is True
    assert result["target_id"] == "obj:broken_cart"


def test_general_interaction_inspect_object():
    result = resolve_general_interaction(
        _state(),
        player_input="I inspect the broken cart.",
    )

    assert result["handled"] is True
    action = result["semantic_action_v2"]
    interaction = result["interaction_result"]

    assert action["kind"] == "inspect"
    assert action["target_id"] == "obj:broken_cart"
    assert interaction["resolved"] is True
    assert interaction["reason"] == "target_inspected"


def test_general_interaction_take_item_requires_inventory_runtime():
    result = resolve_general_interaction(
        _state(),
        player_input="I pick up the rusty key.",
    )

    assert result["handled"] is True
    action = result["semantic_action_v2"]
    interaction = result["interaction_result"]
    inventory = result["inventory_result"]

    assert action["kind"] == "take"
    assert action["target_id"] == "item:rusty_key"
    assert inventory["reason"] == "item_added_to_inventory"
    assert inventory["resolved"] is True
    assert inventory["changed_state"] is True


def test_general_interaction_use_item_on_target():
    result = resolve_general_interaction(
        _state(),
        player_input="I use the rope on the broken cart.",
    )

    action = result["semantic_action_v2"]
    interaction = result["interaction_result"]

    assert action["kind"] == "use"
    assert action["target_id"] == "obj:broken_cart"
    assert action["item_ref"] == "rope"
    assert interaction["resolved"] is True
    assert interaction["reason"] == "use_requires_item_interaction_runtime"


def test_general_interaction_give_item_to_companion():
    result = resolve_general_interaction(
        _state(),
        player_input="I give the small knife to Bran.",
    )

    action = result["semantic_action_v2"]

    assert action["kind"] == "give"
    assert action["target_id"] == "item:small_knife"
    assert action["secondary_target_id"] == "npc:Bran"


def test_unknown_interaction_is_not_handled():
    result = resolve_general_interaction(
        _state(),
        player_input="I do something indescribable.",
    )

    assert result["handled"] is False
    assert result["semantic_action_v2"]["kind"] == "unknown"
