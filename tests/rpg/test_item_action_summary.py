from __future__ import annotations

from app.rpg.session.item_action_summary import build_item_action_summary, summarize_item_actions, summarize_recipe_actions


def test_item_action_summary_marks_equipment_use_salvage_and_sell() -> None:
    item = {
        "item_id": "practice_blade",
        "name": "Practice Blade",
        "item_type": "weapon",
        "type": "weapon",
        "damage": {"slashing": 4},
        "tags": ["metal", "salvageable"],
        "value": {"copper": 12},
    }

    summary = summarize_item_actions(item)
    actions = {action["action"]: action for action in summary["actions"]}

    assert summary["name"] == "Practice Blade"
    assert actions["inspect"]["enabled"] is True
    assert actions["equip"] == {"action": "equip", "enabled": True, "slot": "Weapon", "reason": "equipment_item"}
    assert actions["salvage"]["enabled"] is True
    assert actions["salvage"]["outputs_preview"]
    assert actions["sell"] == {"action": "sell", "enabled": True, "reason": "has_value"}


def test_protected_item_summary_disables_drop_sell_and_salvage() -> None:
    summary = summarize_item_actions({"name": "Journal", "item_type": "quest_item", "type": "quest_item", "value": {"copper": 1}})
    actions = {action["action"]: action for action in summary["actions"]}

    assert summary["protected"] is True
    assert actions["drop"] == {"action": "drop", "enabled": False, "reason": "protected_item"}
    assert actions["sell"] == {"action": "sell", "enabled": False, "reason": "protected_item"}
    assert actions["salvage"]["enabled"] is False


def test_recipe_action_summary_reports_missing_or_enabled_craft() -> None:
    missing = summarize_recipe_actions({"player": {"inventory": []}, "crafting": {"known_recipes": ["torch"]}}, station="campfire")
    ready = summarize_recipe_actions(
        {
            "player": {
                "inventory": [
                    {"item_id": "dry_stick", "name": "Dry Stick", "properties": ["burnable"], "quantity": 1},
                    {"item_id": "cloth", "name": "Cloth", "material_id": "cloth", "quantity": 1},
                    {"item_id": "lamp_oil", "name": "Lamp Oil", "material_id": "lamp_oil", "quantity": 1},
                ]
            },
            "crafting": {"known_recipes": ["torch"]},
        },
        station="campfire",
    )

    assert missing == [
        {
            "action": "craft",
            "recipe_id": "torch",
            "recipe_name": "Craft Torch",
            "enabled": False,
            "error": "missing_ingredients",
            "missing": [
                {"requirement": "burnable property material", "quantity": 1},
                {"requirement": "cloth", "quantity": 1},
                {"requirement": "lamp_oil", "quantity": 1},
            ],
            "station": "campfire",
            "required_station": "campfire",
            "output_preview": {"item_id": "torch", "id": "torch", "name": "Torch", "item_type": "tool", "type": "tool", "quantity": 1, "stackable": False, "capabilities": [{"capability_id": "light_scene", "kind": "tool_use"}], "value": {"copper": 4}, "quality": "standard", "source_history": [{"source": "recipe_craft", "recipe_id": "torch", "recipe_name": "Craft Torch"}], "instance_id": "inst_torch_crafted"},
        }
    ]
    assert ready[0]["enabled"] is True
    assert ready[0]["missing"] == []
    assert ready[0]["output_preview"]["item_id"] == "torch"


def test_build_item_action_summary_returns_trace_and_counts_enabled_actions() -> None:
    state = {
        "player": {
            "inventory": [
                "Health Potion",
                {"item_id": "cloth", "name": "Cloth", "material_id": "cloth", "quantity": 1},
            ]
        },
        "crafting": {"known_recipes": ["torch"]},
    }

    summary = build_item_action_summary(state, station="campfire")

    assert [item["name"] for item in summary["inventory_actions"]] == ["Health Potion", "Cloth"]
    assert summary["recipe_actions"][0]["recipe_id"] == "torch"
    assert summary["trace"] == {
        "event": "item_action_summary_built",
        "inventory_count": 2,
        "recipe_count": 1,
        "enabled_action_count": summary["enabled_action_count"],
        "inventory_changed": True,
        "mechanics_source": "engine_item_action_summary_v1",
    }
    assert summary["mechanics_source"] == "engine_item_action_summary_v1"
    assert summary["enabled_action_count"] >= 4
