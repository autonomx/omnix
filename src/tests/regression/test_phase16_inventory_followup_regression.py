"""Phase 16 — Inventory Follow-up Regression Tests.

Tests for inventory item merging during normalization.
"""

from app.rpg.items.economy import (
    InventoryState,
    InventoryItem,
    InventoryDeterminismValidator,
)


class TestPhase16InventoryFollowupRegression:
    """Regression tests for Phase 16 inventory follow-up fixes."""

    def test_phase16_normalize_state_merges_duplicate_inventory_items(self):
        """Verify normalize_state merges duplicate inventory items."""
        inventory = InventoryState(
            owner_id="p1",
            items=[
                InventoryItem(item_id="healing_potion", quantity=2),
                InventoryItem(item_id="healing_potion", quantity=3),
                InventoryItem(item_id="iron_sword", quantity=1),
            ],
        )
        out = InventoryDeterminismValidator.normalize_state(inventory)
        assert len(out.items) == 2
        assert out.items[0].item_id == "healing_potion"
        assert out.items[0].quantity == 5
        assert out.items[1].item_id == "iron_sword"