from __future__ import annotations

from app.rpg.session.item_objectives import build_item_objectives


def _state() -> dict:
    return {
        "player": {
            "inventory": [
                {
                    "item_id": "practice_blade",
                    "name": "Practice Blade",
                    "item_type": "weapon",
                    "type": "weapon",
                    "damage": {"slashing": 4},
                    "tags": ["metal", "salvageable"],
                    "value": {"copper": 12},
                },
                {"item_id": "dry_stick", "name": "Dry Stick", "properties": ["burnable"], "quantity": 1},
                {"item_id": "cloth", "name": "Cloth", "material_id": "cloth", "quantity": 1},
                {"item_id": "lamp_oil", "name": "Lamp Oil", "material_id": "lamp_oil", "quantity": 1},
            ]
        },
        "crafting": {"known_recipes": ["torch"]},
    }


def test_item_objectives_prioritize_enabled_recipe_and_item_actions() -> None:
    result = build_item_objectives(_state(), station="campfire", limit=5)

    ids = [objective["objective_id"] for objective in result["objectives"]]
    assert ids[0] == "craft:torch"
    assert "equip:practice_blade" in ids
    assert "salvage:practice_blade" in ids
    craft = result["objectives"][0]
    assert craft["action"] == {"action": "craft", "recipe_id": "torch", "station": "campfire"}
    assert result["summary"]["objective_count"] == 5
    assert result["trace"] == {
        "event": "item_objectives_built",
        "objective_count": 5,
        "enabled_action_count": result["summary"]["enabled_action_count"],
        "coverage_score": result["summary"]["coverage_score"],
        "mechanics_source": "engine_item_objectives_v1",
    }


def test_item_objectives_respects_limit_and_empty_inventory() -> None:
    empty = {"player": {"inventory": []}, "crafting": {"known_recipes": []}}

    result = build_item_objectives(empty, limit=2)

    assert len(result["objectives"]) <= 2
    assert result["summary"]["objective_count"] == len(result["objectives"])
    assert result["mechanics_source"] == "engine_item_objectives_v1"
