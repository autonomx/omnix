"""Phase 9.0 — Unit tests for Inventory / Item System."""
from __future__ import annotations

import pytest

from app.rpg.items.item_registry import get_item_definition, list_item_definitions
from app.rpg.items.inventory_state import (
    ensure_inventory_state,
    normalize_inventory_state,
    add_inventory_items,
    remove_inventory_item,
    record_inventory_loot,
    build_inventory_summary,
)
from app.rpg.items.item_effects import apply_item_use
from app.rpg.items.loot_builder import build_loot_from_encounter_state


# ---------------------------------------------------------------------------
# Item Registry Tests
# ---------------------------------------------------------------------------

class TestItemRegistry:
    def test_get_known_item(self):
        item = get_item_definition("gold_coin")
        assert item["item_id"] == "gold_coin"
        assert item["category"] == "currency"

    def test_get_unknown_item(self):
        item = get_item_definition("nonexistent")
        assert item == {}

    def test_list_item_definitions_returns_all(self):
        items = list_item_definitions()
        assert len(items) >= 3
        assert "gold_coin" in items
        assert "healing_potion" in items
        assert "bandit_token" in items

    def test_healing_potion_has_effect(self):
        item = get_item_definition("healing_potion")
        assert "effect" in item
        assert item["effect"]["type"] == "restore_resource"
        assert item["effect"]["amount"] == 10


# ---------------------------------------------------------------------------
# Inventory State Tests
# ---------------------------------------------------------------------------

class TestInventoryState:
    def test_normalize_empty(self):
        result = normalize_inventory_state({})
        assert result["items"] == []
        assert result["equipment"] == {}
        assert result["last_loot"] == []

    def test_ensure_inventory_state_defaults(self):
        player_state = {}
        result = ensure_inventory_state(player_state)
        inventory = result["inventory_state"]
        assert inventory["capacity"] == 50
        assert "items" in inventory

    def test_add_items_stacking(self):
        inv = normalize_inventory_state({})
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 10}])
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 5}])
        assert len(inv["items"]) == 1
        assert inv["items"][0]["qty"] == 15

    def test_remove_items(self):
        inv = normalize_inventory_state({})
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 10}])
        inv = remove_inventory_item(inv, "gold_coin", qty=3)
        assert inv["items"][0]["qty"] == 7

    def test_remove_more_than_available(self):
        inv = normalize_inventory_state({})
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 3}])
        inv = remove_inventory_item(inv, "gold_coin", qty=5)
        assert inv["items"] == []

    def test_remove_unknown_item(self):
        inv = normalize_inventory_state({})
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 1}])
        inv = remove_inventory_item(inv, "unknown_item", qty=1)
        assert len(inv["items"]) == 1

    def test_capacity_limit(self):
        inv = normalize_inventory_state({"capacity": 1})
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 1}])
        inv = add_inventory_items(inv, [{"item_id": "bandit_token", "qty": 1}])
        assert len(inv["items"]) == 1

    def test_build_inventory_summary(self):
        inv = add_inventory_items({}, [{"item_id": "gold_coin", "qty": 5}])
        summary = build_inventory_summary(inv)
        assert summary["slots_used"] == 1
        assert summary["total_item_qty"] == 5


# ---------------------------------------------------------------------------
# Item Effects Tests
# ---------------------------------------------------------------------------

class TestItemEffects:
    def test_use_known_item(self):
        sim_state = {"player_state": {"inventory_state": {}}}
        # First add an item so it can be consumed
        sim_state["player_state"]["inventory_state"] = add_inventory_items(
            {}, [{"item_id": "healing_potion", "qty": 2}]
        )
        result = apply_item_use(sim_state, "healing_potion")
        assert result["result"]["ok"] is True
        assert result["result"]["item_id"] == "healing_potion"
        # One potion should remain
        inv = result["simulation_state"]["player_state"]["inventory_state"]
        assert inv["items"][0]["qty"] == 1

    def test_use_unknown_item(self):
        sim_state = {"player_state": {"inventory_state": {}}}
        result = apply_item_use(sim_state, "nonexistent")
        assert result["result"]["ok"] is False
        assert result["result"]["reason"] == "unknown_item"


# ---------------------------------------------------------------------------
# Loot Builder Tests
# ---------------------------------------------------------------------------

class TestLootBuilder:
    def test_no_loot_for_unresolved(self):
        encounter = {"status": "active", "participants": []}
        assert build_loot_from_encounter_state(encounter) == []

    def test_no_loot_without_hostiles(self):
        encounter = {"status": "resolved", "participants": [{"disposition": "friendly"}]}
        assert build_loot_from_encounter_state(encounter) == []

    def test_gold_from_single_hostile(self):
        encounter = {"status": "resolved", "participants": [{"role": "enemy"}]}
        loot = build_loot_from_encounter_state(encounter)
        gold = [l for l in loot if l["item_id"] == "gold_coin"]
        assert gold[0]["qty"] == 3

    def test_bandit_token_from_two_hostiles(self):
        encounter = {
            "status": "resolved",
            "participants": [{"disposition": "hostile"}, {"disposition": "hostile"}],
        }
        loot = build_loot_from_encounter_state(encounter)
        tokens = [l for l in loot if l["item_id"] == "bandit_token"]
        assert tokens[0]["qty"] == 1

    def test_healing_potion_from_three_hostiles(self):
        encounter = {
            "status": "resolved",
            "participants": [
                {"disposition": "hostile"},
                {"disposition": "hostile"},
                {"disposition": "hostile"},
            ],
        }
        loot = build_loot_from_encounter_state(encounter)
        potions = [l for l in loot if l["item_id"] == "healing_potion"]
        assert potions[0]["qty"] == 1