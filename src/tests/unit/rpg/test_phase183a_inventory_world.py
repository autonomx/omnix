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
from app.rpg.economy.currency import normalize_currency
from app.rpg.economy.transactions import enrich_action_with_registry_price
from app.rpg.economy.transaction_effects import apply_transaction_effects
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


from app.rpg.session.runtime import (
    _apply_action_resource_requirements,
    _apply_starting_resources_to_player_state,
)


class TestCanonicalResources:
    def test_starting_resources_bridge_into_player_currency(self):
        simulation_state = {}
        setup_payload = {
            "starting_resources": {
                "gold": 75,
                "health_potions": 2,
            }
        }

        out = _apply_starting_resources_to_player_state(simulation_state, setup_payload)
        player_state = out["player_state"]
        inventory_state = player_state["inventory_state"]

        assert inventory_state["currency"]["gold"] == 75
        assert any(item["item_id"] == "health_potions" for item in inventory_state["items"])

    def test_action_cost_blocks_when_insufficient_gold(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0},
                    "last_loot": [],
                }
            }
        }
        action = {
            "action_type": "trade",
            "gold_cost": 5,
        }

        out = _apply_action_resource_requirements(simulation_state, action)

        assert out["ok"] is False
        assert out["result"]["blocked"] is True
        assert out["result"]["blocked_reason"] == "insufficient_currency"

    def test_action_cost_deducts_gold_when_affordable(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 9},
                    "last_loot": [],
                }
            }
        }
        action = {
            "action_type": "trade",
            "gold_cost": 5,
        }

        out = _apply_action_resource_requirements(simulation_state, action)
        inventory_state = out["simulation_state"]["player_state"]["inventory_state"]

        assert out["ok"] is True
        assert inventory_state["currency"]["gold"] == 4
        assert out["result"]["resource_changes"]["currency"]["gold"] == -5

    def test_action_cost_supports_structured_currency(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 1, "silver": 0, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = {
            "action_type": "buy",
            "currency_cost": {"silver": 9, "copper": 5},
        }

        out = _apply_action_resource_requirements(simulation_state, action)
        inventory_state = out["simulation_state"]["player_state"]["inventory_state"]

        assert out["ok"] is True
        assert normalize_currency(inventory_state["currency"]) == {"gold": 0, "silver": 0, "copper": 5}

    def test_action_cost_blocks_with_structured_currency(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 4, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = {
            "action_type": "buy",
            "currency_cost": {"silver": 4, "copper": 1},
        }

        out = _apply_action_resource_requirements(simulation_state, action)

        assert out["ok"] is False
        assert out["result"]["blocked"] is True
        assert out["result"]["blocked_reason"] == "insufficient_currency"

    def test_buy_action_uses_registry_price_before_spend_gate(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 2, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = enrich_action_with_registry_price({
            "action_type": "buy",
            "item_id": "torch",
        })

        out = _apply_action_resource_requirements(simulation_state, action)
        inventory_state = out["simulation_state"]["player_state"]["inventory_state"]

        assert out["ok"] is True
        assert normalize_currency(inventory_state["currency"]) == {"gold": 0, "silver": 1, "copper": 0}

    def test_rent_room_action_blocks_from_registry_price_when_insufficient(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 1, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = enrich_action_with_registry_price({
            "action_type": "rent_room",
        })

        out = _apply_action_resource_requirements(simulation_state, action)

        assert out["ok"] is False
        assert out["result"]["blocked"] is True
        assert out["result"]["blocked_reason"] == "insufficient_currency"
        assert out["result"]["requirements"]["currency"] == {"gold": 0, "silver": 2, "copper": 0}

    def test_registry_purchase_followed_by_effect_adds_item(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 2, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = enrich_action_with_registry_price({
            "action_type": "buy",
            "item_id": "torch",
        })

        gated = _apply_action_resource_requirements(simulation_state, action)
        assert gated["ok"] is True

        effect_out = apply_transaction_effects(
            gated["simulation_state"],
            action,
            {"transaction_kind": "item_purchase"},
        )

        inventory_state = effect_out["simulation_state"]["player_state"]["inventory_state"]
        assert any(item["item_id"] == "torch" for item in inventory_state["items"])

    def test_registry_service_followed_by_effect_updates_lodging(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 5, "hunger": 0, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 3, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = enrich_action_with_registry_price({
            "action_type": "rent_room",
        })

        gated = _apply_action_resource_requirements(simulation_state, action)
        assert gated["ok"] is True

        effect_out = apply_transaction_effects(
            gated["simulation_state"],
            action,
            {"transaction_kind": "service_purchase"},
        )

        player_state = effect_out["simulation_state"]["player_state"]
        assert player_state["lodging"] == "private_room"
        assert "rested" in player_state["statuses"]
