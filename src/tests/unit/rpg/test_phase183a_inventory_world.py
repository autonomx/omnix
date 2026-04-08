"""Phase 18.3A — Unit tests for inventory world grounding."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.rpg.items.generated_item_builder import (
    build_item_definition_from_llm,
    clamp_generated_item_stats,
    derive_item_power_band,
)
from app.rpg.items.inventory_state import (
    equip_inventory_item,
    find_inventory_item,
    get_equipped_armor,
    get_equipped_weapon,
    normalize_inventory_state,
    unequip_inventory_slot,
)
from app.rpg.items.item_registry import (
    get_item_definition,
    normalize_item_definition,
)
from app.rpg.items.item_stats import (
    get_weapon_attack_stat,
    get_weapon_skill,
    is_armor,
    is_shield,
    is_weapon,
    normalize_item_stats,
)
from app.rpg.items.world_items import (
    drop_world_item,
    ensure_world_item_state,
    list_scene_items,
    pickup_world_item,
    spawn_world_item,
)


class TestWorldItems:
    def test_ensure_world_item_state(self):
        sim = ensure_world_item_state({})
        assert "world_items" in sim
        assert "by_location" in sim["world_items"]

    def test_spawn_world_item(self):
        sim = ensure_world_item_state({})
        sim = spawn_world_item(sim, "loc:market", {"item_id": "iron_sword", "name": "Iron Sword"})
        items = sim["world_items"]["by_location"]["loc:market"]
        assert len(items) == 1
        assert items[0]["item_id"] == "iron_sword"

    def test_pickup_world_item(self):
        sim = ensure_world_item_state({})
        sim = spawn_world_item(sim, "loc:cave", {"item_id": "healing_potion"})
        instance_id = sim["world_items"]["by_location"]["loc:cave"][0]["instance_id"]
        sim = pickup_world_item(sim, instance_id)
        assert sim["_picked_up_item"]["item_id"] == "healing_potion"
        assert len(sim["world_items"]["by_location"]["loc:cave"]) == 0

    def test_drop_world_item(self):
        sim = ensure_world_item_state({"player_state": {"current_scene_id": "loc:town"}})
        sim = drop_world_item(sim, "gold_coin", "loc:town", qty=5)
        items = list_scene_items(sim, "loc:town")
        assert len(items) >= 1

    def test_list_scene_items_empty(self):
        sim = ensure_world_item_state({})
        items = list_scene_items(sim, "nonexistent")
        assert items == []

    def test_pickup_nonexistent(self):
        sim = ensure_world_item_state({})
        sim = pickup_world_item(sim, "fake_id")
        assert sim["_picked_up_item"] == {}


class TestEquipment:
    def test_equip_item(self):
        inv = normalize_inventory_state({"items": [{"item_id": "iron_sword", "qty": 1, "name": "Iron Sword", "equipment": {"slot": "main_hand"}}]})
        inv = equip_inventory_item(inv, "iron_sword")
        assert "main_hand" in inv["equipment"]
        assert inv["equipment"]["main_hand"]["item_id"] == "iron_sword"

    def test_unequip_item(self):
        inv = normalize_inventory_state({"items": [{"item_id": "iron_sword", "qty": 1}], "equipment": {"main_hand": {"item_id": "iron_sword", "qty": 1}}})
        inv = unequip_inventory_slot(inv, "main_hand")
        assert "main_hand" not in inv["equipment"]

    def test_find_item(self):
        inv = normalize_inventory_state({"items": [{"item_id": "healing_potion", "qty": 3, "name": "Healing Potion"}]})
        found = find_inventory_item(inv, "healing_potion")
        assert found["item_id"] == "healing_potion"

    def test_find_missing(self):
        inv = normalize_inventory_state({"items": []})
        found = find_inventory_item(inv, "nonexistent")
        assert found == {}

    def test_get_equipped_weapon(self):
        inv = normalize_inventory_state({"equipment": {"main_hand": {"item_id": "rusty_sword", "qty": 1, "name": "Rusty Sword"}}})
        weapon = get_equipped_weapon(inv)
        assert weapon["item_id"] == "rusty_sword"

    def test_get_equipped_armor(self):
        inv = normalize_inventory_state({"equipment": {"off_hand": {"item_id": "wooden_shield", "qty": 1, "combat_stats": {"defense_bonus": 3, "block_bonus": 8}}}})
        armor = get_equipped_armor(inv)
        assert len(armor) >= 1


class TestItemStats:
    def test_normalize_item_stats(self):
        item = normalize_item_stats({"combat_stats": {"damage": 10}})
        assert item["combat_stats"]["damage"] == 10
        assert "equipment" in item
        assert "quality" in item

    def test_is_weapon(self):
        assert is_weapon({"combat_stats": {"damage": 10}})
        assert not is_weapon({"combat_stats": {"damage": 0}})

    def test_is_armor(self):
        assert is_armor({"combat_stats": {"defense_bonus": 5}})
        assert not is_armor({"combat_stats": {"defense_bonus": 0}})

    def test_is_shield(self):
        assert is_shield({"combat_stats": {"block_bonus": 8}})

    def test_get_weapon_skill_sword(self):
        assert get_weapon_skill({"combat_stats": {"weapon_type": "sword"}}) == "swordsmanship"

    def test_get_weapon_skill_bow(self):
        assert get_weapon_skill({"combat_stats": {"weapon_type": "bow"}}) == "archery"

    def test_get_weapon_attack_stat(self):
        assert get_weapon_attack_stat({"combat_stats": {"weapon_type": "pistol"}}) == "dexterity"


class TestGeneratedItemBuilder:
    def test_build_from_llm(self):
        item = build_item_definition_from_llm({"name": "Magic Sword", "category": "weapon", "combat_stats": {"damage": 30, "weapon_type": "sword"}})
        assert item["generated_by"] == "llm"
        assert item["stat_origin"] == "generated"
        assert "item_id" in item

    def test_clamp_damage(self):
        item = clamp_generated_item_stats({"combat_stats": {"damage": 999}, "quality": {"rarity": "common"}}, world_tier=0)
        assert item["combat_stats"]["damage"] <= 20

    def test_power_band_scales(self):
        band0 = derive_item_power_band(0, "common")
        band4 = derive_item_power_band(4, "legendary")
        assert band4["max_damage"] > band0["max_damage"]

    def test_deterministic_id(self):
        item1 = build_item_definition_from_llm({"name": "Axe", "category": "weapon"})
        item2 = build_item_definition_from_llm({"name": "Axe", "category": "weapon"})
        assert item1["item_id"] == item2["item_id"]


class TestItemRegistry:
    def test_new_items_exist(self):
        for item_id in ["rusty_sword", "iron_sword", "wooden_shield", "iron_shield", "short_bow", "pistol_9mm", "combat_knife"]:
            item = get_item_definition(item_id)
            assert item, f"Missing item: {item_id}"
            assert item["item_id"] == item_id

    def test_normalize_item_definition(self):
        item = normalize_item_definition({"item_id": "test", "name": "Test"})
        assert "combat_stats" in item
        assert "quality" in item

    def test_weapon_stats(self):
        sword = get_item_definition("iron_sword")
        assert sword["combat_stats"]["damage"] == 28
        bow = get_item_definition("short_bow")
        assert bow["combat_stats"]["damage"] == 15
