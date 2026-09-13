from __future__ import annotations

from app.rpg.session.item_modifications import apply_item_modification, preview_item_modification


def _inventory() -> list[dict]:
    return [
        {"item_id": "iron", "name": "Iron scrap", "material_id": "iron", "item_type": "crafting_material", "quantity": 2, "stackable": True},
        {"item_id": "leather", "name": "Leather strip", "material_id": "leather", "item_type": "crafting_material", "quantity": 1, "stackable": True},
        {"item_id": "cloth", "name": "Cloth scrap", "material_id": "cloth", "item_type": "crafting_material", "quantity": 1, "stackable": True},
    ]


def test_preview_rejects_unknown_modification() -> None:
    result = preview_item_modification({"name": "Practice Blade", "item_type": "weapon"}, _inventory(), "unknown_mod")

    assert result["ok"] is False
    assert result["error"] == "unknown_modification"


def test_preview_rejects_invalid_target_type() -> None:
    result = preview_item_modification({"name": "Travel Coat", "item_type": "armor"}, _inventory(), "edge_damage_minor")

    assert result["ok"] is False
    assert result["error"] == "invalid_modification_target"
    assert result["valid_item_types"] == ["weapon"]


def test_preview_reports_missing_materials() -> None:
    result = preview_item_modification({"name": "Practice Blade", "item_type": "weapon"}, [], "edge_damage_minor")

    assert result["ok"] is False
    assert result["error"] == "missing_modification_materials"
    assert result["missing"] == [{"material_id": "iron", "required": 1, "available": 0}]


def test_apply_weapon_modification_consumes_material_and_updates_damage() -> None:
    inventory = _inventory()
    item = {"item_id": "practice_blade", "name": "Practice Blade", "item_type": "weapon", "damage": {"slashing": 2}}

    result = apply_item_modification(item, inventory, "edge_damage_minor")

    assert result["ok"] is True
    assert result["item"]["damage"] == {"slashing": 3}
    assert result["item"]["modifications"] == [{"mod_id": "edge_damage_minor", "name": "Honed Edge", "mechanics_source": "engine_item_modification_v1"}]
    assert inventory[0]["quantity"] == 1
    assert result["consumed_materials"] == [{"material_id": "iron", "quantity": 1, "name": "Iron scrap"}]
    assert result["trace"]["event"] == "item_modified"
    assert result["trace"]["mod_id"] == "edge_damage_minor"


def test_apply_armor_modification_updates_defense_and_prevents_duplicate() -> None:
    inventory = _inventory()
    item = {"item_id": "travel_coat", "name": "Travel Coat", "item_type": "armor", "defense": {"slashing": 1}}

    result = apply_item_modification(item, inventory, "reinforced_armor_minor")
    duplicate = preview_item_modification(result["item"], inventory, "reinforced_armor_minor")

    assert result["ok"] is True
    assert result["item"]["defense"] == {"slashing": 2}
    assert inventory[1]["quantity"] == 0 or all(entry.get("material_id") != "leather" for entry in inventory)
    assert duplicate["ok"] is False
    assert duplicate["error"] == "modification_already_applied"


def test_apply_lining_modification_updates_resistance() -> None:
    inventory = _inventory()
    item = {"item_id": "travel_coat", "name": "Travel Coat", "item_type": "clothing"}

    result = apply_item_modification(item, inventory, "insulated_lining_minor")

    assert result["ok"] is True
    assert result["item"]["resistances"] == {"cold": 1}
    assert result["trace"]["effects"] == [{"op": "add_resistance", "damage_type": "cold", "amount": 1}]
