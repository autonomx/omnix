"""Phase 9.0 — Regression tests for Inventory / Item System.

These tests guard against regressions in inventory behavior,
including stack merging, capacity limits, and save migration compatibility.
"""
from __future__ import annotations

import pytest

from app.rpg.items.inventory_state import (
    add_inventory_items,
    build_inventory_summary,
    normalize_inventory_state,
    record_inventory_loot,
    remove_inventory_item,
)
from app.rpg.items.item_registry import get_item_definition


class TestInventoryRegression:
    """Regression guards for inventory state management."""

    def test_stack_merge_preserves_item_id(self):
        """Stack merging should not change the item_id of existing stacks."""
        inv = add_inventory_items({}, [{"item_id": "gold_coin", "qty": 10}])
        inv = add_inventory_items(inv, [{"item_id": "gold_coin", "qty": 5}])
        assert inv["items"][0]["item_id"] == "gold_coin"
        assert inv["items"][0]["qty"] == 15

    def test_different_items_create_separate_stacks(self):
        """Non-stackable / different item_ids should create separate stack entries."""
        inv = add_inventory_items({}, [
            {"item_id": "gold_coin", "qty": 10},
            {"item_id": "bandit_token", "qty": 2},
        ])
        assert len(inv["items"]) == 2

    def test_inventory_normalization_strips_unknown_tags(self):
        """Tags beyond 8 should be trimmed on normalization."""
        raw = {
            "items": [{
                "item_id": "gold_coin",
                "qty": 1,
                "name": "Gold Coin",
                "tags": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            }],
        }
        norm = normalize_inventory_state(raw)
        tags = norm["items"][0]["tags"]
        assert len(tags) <= 8

    def test_record_loot_overwrites_last_loot(self):
        """record_inventory_loot should set last_loot to the latest loot items."""
        inv = record_inventory_loot({}, [{"item_id": "gold_coin", "qty": 5}])
        assert len(inv["last_loot"]) == 1
        assert inv["last_loot"][0]["item_id"] == "gold_coin"
        # Now add different loot — last_loot should update
        inv = record_inventory_loot(inv, [{"item_id": "healing_potion", "qty": 1}])
        assert inv["last_loot"][0]["item_id"] == "healing_potion"

    def test_build_summary_accurate_with_many_items(self):
        """Summary should reflect total kind count and aggregate quantity."""
        inv = add_inventory_items({}, [
            {"item_id": "gold_coin", "qty": 100},
            {"item_id": "healing_potion", "qty": 3},
            {"item_id": "bandit_token", "qty": 7},
        ])
        summary = build_inventory_summary(inv)
        assert summary["slots_used"] == 3
        assert summary["total_item_qty"] == 110

    def test_empty_inventory_has_zero_summary(self):
        """An empty inventory should have zeros in all summary fields."""
        summary = build_inventory_summary({})
        assert summary["slots_used"] == 0
        assert summary["total_item_qty"] == 0
        assert summary["last_loot_count"] == 0

    def test_remove_preserves_other_stack(self):
        """Removing all of one item should leave other items untouched."""
        inv = add_inventory_items({}, [
            {"item_id": "gold_coin", "qty": 5},
            {"item_id": "healing_potion", "qty": 2},
        ])
        inv = remove_inventory_item(inv, "gold_coin", qty=5)
        assert len(inv["items"]) == 1
        assert inv["items"][0]["item_id"] == "healing_potion"
        assert inv["items"][0]["qty"] == 2


class TestMigrationRegression:
    """Guard against save migration incompatibilities."""

    def test_v3_to_v4_adds_inventory_state(self):
        """Migration v3_to_v4 should inject a default inventory_state."""
        from app.rpg.persistence.migrations.v3_to_v4 import migrate_v3_to_v4

        package_v3 = {
            "schema_version": 3,
            "state": {
                "simulation_state": {
                    "player_state": {},
                },
            },
        }
        migrated = migrate_v3_to_v4(package_v3)
        assert migrated["schema_version"] == 4
        player_state = migrated["state"]["simulation_state"]["player_state"]
        assert "inventory_state" in player_state
        inv = player_state["inventory_state"]
        assert inv["items"] == []
        assert inv["capacity"] == 50