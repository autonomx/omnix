from __future__ import annotations

from app.rpg.session.item_system import (
    apply_item_fiction_proposal,
    build_item_catalog,
    build_starting_equipment,
    build_starting_inventory,
    craft_item,
    make_armor_template,
    make_weapon_template,
    upgrade_item_instance,
    validate_item_template,
)


def test_weapon_template_has_valid_damage_stats() -> None:
    weapon = make_weapon_template(
        "test_sword",
        "Test Sword",
        weapon_type="sword",
        damage_type="slashing",
        base_damage=7,
        level=3,
        rarity="rare",
    )

    validation = validate_item_template(weapon)

    assert validation.ok is True
    assert weapon["item_type"] == "weapon"
    assert weapon["weapon_type"] == "sword"
    assert weapon["damage"] == [{"type": "slashing", "amount": 11}]
    assert weapon["upgrade"]["max_upgrade_level"] == 5


def test_armor_template_has_valid_defense_stats() -> None:
    armor = make_armor_template(
        "test_mail",
        "Test Mail",
        armor_type="medium",
        defense_type="physical",
        base_defense=5,
        level=4,
        rarity="uncommon",
    )

    validation = validate_item_template(armor)

    assert validation.ok is True
    assert armor["item_type"] == "armor"
    assert armor["armor_type"] == "medium"
    assert armor["defense"] == [{"type": "physical", "amount": 7}]


def test_invalid_weapon_damage_is_rejected() -> None:
    weapon = make_weapon_template(
        "bad_wand",
        "Bad Wand",
        weapon_type="wand",
        damage_type="arcane",
        base_damage=4,
    )
    weapon["damage"] = [{"type": "friendship", "amount": 4}]

    validation = validate_item_template(weapon)

    assert validation.ok is False
    assert validation.error == "unsupported_damage_type"


def test_starting_inventory_has_rarity_levels_and_combat_stats() -> None:
    inventory = build_starting_inventory("classic_fantasy", build_id="ranger", level=1)
    by_id = {item["id"]: item for item in inventory}

    assert {"ration", "torch", "iron_dagger", "simple_bow", "journal"} <= set(by_id)
    assert by_id["iron_dagger"]["rarity"] == "common"
    assert by_id["iron_dagger"]["level"] == 1
    assert by_id["iron_dagger"]["damage"] == [{"type": "piercing", "amount": 4}]
    assert by_id["simple_bow"]["slot"] == "Ranged"
    assert by_id["ration"]["effects"][0]["resource"] == "stamina"
    assert by_id["keenleaf"]["item_type"] == "crafting_material"


def test_genre_catalog_names_items_without_changing_mechanics() -> None:
    fantasy = build_item_catalog("classic_fantasy")
    cyberpunk = build_item_catalog("cyberpunk")

    assert fantasy["iron_dagger"]["name"] == "Iron dagger"
    assert cyberpunk["iron_dagger"]["name"] == "Streetline mono-knife"
    assert fantasy["iron_dagger"]["damage"] == cyberpunk["iron_dagger"]["damage"]
    assert fantasy["simple_bow"]["weapon_type"] == cyberpunk["simple_bow"]["weapon_type"]


def test_equipment_carries_item_stats_for_ui_and_combat() -> None:
    equipment = build_starting_equipment("classic_fantasy", build_id="warrior", level=1)
    by_slot = {item["slot"]: item for item in equipment}

    assert by_slot["Weapon"]["item_id"] == "iron_dagger"
    assert by_slot["Weapon"]["damage"] == [{"type": "piercing", "amount": 4}]
    assert by_slot["Armor"]["item_id"] == "leather_armor"
    assert by_slot["Armor"]["defense"] == [{"type": "physical", "amount": 3}]


def test_ai_item_fiction_can_rename_but_not_change_mechanics() -> None:
    item = build_item_catalog("classic_fantasy")["iron_dagger"]
    result = apply_item_fiction_proposal(
        item,
        {
            "name": "Widow's Whisper",
            "description": "A slim blade with a black cord grip.",
            "damage": [{"type": "necrotic", "amount": 999}],
            "rarity": "legendary",
            "level": 50,
            "flavor_tags": ["assassin", "quiet"],
        },
    )

    assert result.ok is True
    assert result.item["name"] == "Widow's Whisper"
    assert result.item["description"] == "A slim blade with a black cord grip."
    assert result.item["flavor_tags"] == ["assassin", "quiet"]
    assert result.item["damage"] == item["damage"]
    assert result.item["rarity"] == "common"
    assert result.item["level"] == 1
    assert set(result.ignored_fields) >= {"damage", "rarity", "level"}


def test_upgrade_item_requires_materials_and_improves_damage() -> None:
    catalog = build_item_catalog("classic_fantasy")
    dagger = catalog["iron_dagger"]
    missing = upgrade_item_instance(dagger, [])

    assert missing.ok is False
    assert missing.error == "missing_upgrade_materials"

    upgraded = upgrade_item_instance(dagger, [{"id": "iron_ingot", "name": "Iron ingot", "item_type": "crafting_material", "quantity": 2}])

    assert upgraded.ok is True
    assert upgraded.item is not None
    assert upgraded.item["name"] == "Iron dagger +1"
    assert upgraded.item["upgrade"]["upgrade_level"] == 1
    assert upgraded.item["damage"] == [{"type": "piercing", "amount": 5}]
    assert upgraded.inventory[0]["quantity"] == 1


def test_crafting_consumes_materials_and_adds_result_item() -> None:
    result = craft_item(
        "healing_potion",
        [
            {"id": "keenleaf", "name": "Keenleaf", "item_type": "crafting_material", "quantity": 2},
            {"id": "waterskin", "name": "Waterskin", "item_type": "supply", "quantity": 1},
        ],
    )

    assert result.ok is True
    assert result.item is not None
    assert result.item["id"] == "health_potion"
    assert result.added_items[0]["effects"][0]["resource"] == "hp"
    assert result.consumed_materials == [{"item_id": "keenleaf", "quantity": 2}, {"item_id": "waterskin", "quantity": 1}]
    assert [item["id"] for item in result.inventory] == ["health_potion"]
