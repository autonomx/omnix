from __future__ import annotations

from app.rpg.session.item_pickups import apply_scene_item_pickup, list_scene_item_nodes


def test_list_scene_item_nodes_normalizes_remaining_and_depleted_state() -> None:
    state = {
        "scene_state": {
            "item_nodes": [
                {"id": "satchel", "name": "Travel Satchel", "remaining": 2},
                {"id": "spent", "name": "Spent Cache", "remaining": 0},
            ]
        }
    }

    nodes = list_scene_item_nodes(state)

    assert nodes[0]["node_id"] == "satchel"
    assert nodes[0]["remaining"] == 2
    assert nodes[0]["depleted"] is False
    assert nodes[1]["depleted"] is True


def test_apply_scene_item_pickup_adds_explicit_outputs_and_depletes_node() -> None:
    state = {
        "player": {"inventory": []},
        "scene_state": {
            "item_nodes": [
                {
                    "id": "road_bundle",
                    "name": "Road Bundle",
                    "outputs": [
                        {"item_id": "travel_ration", "name": "Travel ration", "item_type": "consumable", "quantity": 1, "stackable": True}
                    ],
                }
            ]
        },
    }

    result = apply_scene_item_pickup(state, "road_bundle", seed="pickup-seed")

    assert result["ok"] is True
    assert state["player"]["inventory"][0]["item_id"] == "travel_ration"
    assert state["scene_state"]["item_nodes"][0]["depleted"] is True
    assert result["trace"]["event"] == "scene_item_picked_up"
    assert state["mechanics"]["pickup_traces"][0] == result["trace"]


def test_apply_scene_item_pickup_uses_reward_table_when_no_explicit_outputs() -> None:
    state = {
        "player": {"inventory": []},
        "scene_state": {
            "item_nodes": [
                {"id": "forest_bundle", "name": "Forest Bundle", "source_id": "forest_cache", "remaining": 1}
            ]
        },
    }

    result = apply_scene_item_pickup(state, "forest_bundle", seed="forest-seed")

    assert result["ok"] is True
    assert result["outputs"]
    assert result["trace"]["reward_trace"]["source_id"] == "forest_cache"
    assert state["mechanics"]["item_traces"][0]["mechanics_source"] == "engine_item_pickup_v1"


def test_apply_scene_item_pickup_merges_stackable_outputs() -> None:
    state = {
        "player": {
            "inventory": [
                {"item_id": "iron", "name": "Iron scrap", "item_type": "crafting_material", "material_id": "iron", "quantity": 2, "stackable": True}
            ]
        },
        "scene_state": {
            "item_nodes": [
                {
                    "id": "iron_bundle",
                    "outputs": [
                        {"item_id": "iron", "name": "Iron scrap", "item_type": "crafting_material", "material_id": "iron", "quantity": 3, "stackable": True}
                    ],
                }
            ]
        },
    }

    result = apply_scene_item_pickup(state, "iron_bundle")

    assert result["ok"] is True
    assert len(state["player"]["inventory"]) == 1
    assert state["player"]["inventory"][0]["quantity"] == 5


def test_apply_scene_item_pickup_rejects_missing_or_depleted_node() -> None:
    state = {
        "player": {"inventory": []},
        "scene_state": {"item_nodes": [{"id": "empty_bundle", "remaining": 0}]},
    }

    missing = apply_scene_item_pickup(state, "unknown")
    depleted = apply_scene_item_pickup(state, "empty_bundle")

    assert missing["ok"] is False
    assert missing["error"] == "pickup_node_not_found"
    assert depleted["ok"] is False
    assert depleted["error"] == "pickup_node_depleted"
