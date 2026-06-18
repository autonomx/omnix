from __future__ import annotations

from app.rpg.session.inventory_items import (
    find_inventory_item,
    is_protected_item,
    normalize_inventory_items,
    normalize_player_inventory,
)


def test_normalize_legacy_inventory_strings_to_item_instances() -> None:
    inventory, trace = normalize_inventory_items(["Rope", "Journal"])

    assert trace["changed"] is True
    assert trace["legacy_count"] == 2
    assert inventory[0]["item_id"] == "rope"
    assert inventory[0]["instance_id"] == "inst_rope_1"
    assert inventory[0]["display"] == {"name": "Rope"}
    assert inventory[0]["quantity"] == 1
    assert inventory[0]["source_history"] == [{"source": "legacy_inventory_string", "name": "Rope"}]
    assert inventory[1]["item_id"] == "journal"
    assert inventory[1]["item_type"] == "quest_item"
    assert inventory[1]["protected"] is True
    assert is_protected_item(inventory[1]) is True


def test_stackable_materials_merge_while_unique_gear_stays_separate() -> None:
    inventory, trace = normalize_inventory_items(
        [
            {"id": "iron_a", "name": "Iron scrap", "quantity": 2, "material_id": "iron", "item_type": "crafting_material"},
            {"id": "iron_b", "name": "Moon Iron", "quantity": 3, "material_id": "iron", "item_type": "crafting_material"},
            {"id": "old_sword", "name": "Old Sword", "type": "weapon"},
            {"id": "old_sword", "name": "Old Sword", "type": "weapon"},
        ]
    )

    assert trace["output_count"] == 3
    assert trace["merged_count"] == 1
    iron = inventory[0]
    assert iron["material_id"] == "iron"
    assert iron["quantity"] == 5
    assert iron["stackable"] is True
    swords = [item for item in inventory if item.get("item_id") == "old_sword"]
    assert len(swords) == 2
    assert swords[0]["instance_id"] == "inst_old_sword_3"
    assert swords[1]["instance_id"] == "inst_old_sword_4"


def test_find_inventory_item_matches_display_id_and_instance_id() -> None:
    player = {
        "inventory": [
            {"id": "rope", "name": "Braided Rope", "type": "tool"},
            {"name": "Moon-Touched Iron Fragments", "material_id": "iron", "quantity": 2, "item_type": "crafting_material"},
        ]
    }

    inventory, index, item = find_inventory_item(player, "iron")
    assert index == 1
    assert item is inventory[1]
    assert item["item_id"] == "iron"

    _, index, item = find_inventory_item(player, "inst_rope_1")
    assert index == 0
    assert item["name"] == "Braided Rope"


def test_normalize_player_inventory_mutates_player_and_reports_noop_second_pass() -> None:
    player = {"inventory": ["Rope"]}

    first = normalize_player_inventory(player)
    second = normalize_player_inventory(player)

    assert first["changed"] is True
    assert first["inventory"][0]["item_id"] == "rope"
    assert second["changed"] is False
    assert player["inventory"] == second["inventory"]
