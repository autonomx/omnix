"""Phase 16 — Inventory Fix Regression Tests.

Tests for equipment validation, inventory normalization,
and item definition safety.
"""

from app.rpg.items.economy import (
    EquipmentManager,
    InventoryDeterminismValidator,
    InventoryItem,
    InventoryState,
    ItemDefinition,
    ShopManager,
    ShopState,
)


class TestPhase16InventoryFixRegression:
    """Regression tests for Phase 16 inventory fixes."""

    def test_phase16_equip_requires_item_presence_and_valid_definition(self):
        """Verify equip requires item presence and valid definition."""
        inventory = InventoryState(owner_id="p1", items=[InventoryItem(item_id="iron_sword", quantity=1)])
        definitions = {
            "iron_sword": ItemDefinition(
                item_id="iron_sword",
                name="Iron Sword",
                equippable=True,
                slot="main_hand",
            )
        }
        bad = EquipmentManager.equip(inventory, "missing", "main_hand", definitions)
        assert bad["success"] is False

        ok = EquipmentManager.equip(inventory, "iron_sword", "main_hand", definitions)
        assert ok["success"] is True
        assert inventory.equipment["main_hand"] == "iron_sword"

    def test_phase16_normalize_state_drops_invalid_equipment(self):
        """Verify normalize_state drops invalid equipment."""
        inventory = InventoryState(
            owner_id="p1",
            items=[InventoryItem(item_id="iron_sword", quantity=1)],
            equipment={"head": "iron_sword", "main_hand": "missing"},
        )
        definitions = {
            "iron_sword": ItemDefinition(
                item_id="iron_sword",
                name="Iron Sword",
                equippable=True,
                slot="main_hand",
            )
        }
        out = InventoryDeterminismValidator.normalize_state(inventory, definitions)
        assert out.equipment == {}

    def test_phase16_validate_bounds_catches_equipped_item_missing_from_inventory(self):
        """Verify validate_bounds catches equipped items missing from inventory."""
        inventory = InventoryState(
            owner_id="p1",
            items=[],
            equipment={"main_hand": "missing_sword"},
        )
        violations = InventoryDeterminismValidator.validate_bounds(inventory)
        assert any("equipped item missing from inventory" in v for v in violations)

    def test_phase16_validate_bounds_catches_equipped_item_missing_definition(self):
        """Verify validate_bounds catches equipped items missing definition."""
        inventory = InventoryState(
            owner_id="p1",
            items=[InventoryItem(item_id="iron_sword", quantity=1)],
            equipment={"main_hand": "iron_sword"},
        )
        definitions: dict = {}
        violations = InventoryDeterminismValidator.validate_bounds(inventory, definitions)
        assert any("equipped item missing definition" in v for v in violations)

    def test_phase16_normalize_state_sorts_items(self):
        """Verify normalize_state sorts items by item_id."""
        inventory = InventoryState(
            owner_id="p1",
            items=[
                InventoryItem(item_id="zebra_potion", quantity=2),
                InventoryItem(item_id="apple", quantity=5),
                InventoryItem(item_id="mango", quantity=1),
            ],
        )
        out = InventoryDeterminismValidator.normalize_state(inventory)
        ids = [i.item_id for i in out.items]
        assert ids == ["apple", "mango", "zebra_potion"]

    def test_phase16_shop_buy_item_checks_definition(self):
        """Verify shop buy_item checks item definition if provided."""
        player_inv = InventoryState(owner_id="p1", currency={"gold": 100})
        shop = ShopState(shop_id="shop1", buy_modifier=1.0)
        result = ShopManager.buy_item(player_inv, shop, "unknown_item", 50, item_definitions={})
        assert result["success"] is False
        assert "unknown item definition" in result.get("reason", "")

    def test_phase16_shop_sell_item_checks_definition(self):
        """Verify shop sell_item checks item definition if provided."""
        player_inv = InventoryState(owner_id="p1", items=[InventoryItem(item_id="iron_sword", quantity=1)])
        shop = ShopState(shop_id="shop1", sell_modifier=0.5)
        result = ShopManager.sell_item(player_inv, shop, "iron_sword", 50, item_definitions={})
        assert result["success"] is False
        assert "unknown item definition" in result.get("reason", "")

    def test_phase16_equip_checks_item_equippable_flag(self):
        """Verify equip checks item equippable flag."""
        inventory = InventoryState(owner_id="p1", items=[InventoryItem(item_id="potion", quantity=1)])
        definitions = {
            "potion": ItemDefinition(
                item_id="potion",
                name="Potion",
                equippable=False,
                slot="",
            )
        }
        result = EquipmentManager.equip(inventory, "potion", "main_hand", definitions)
        assert result["success"] is False
        assert "not equippable" in result.get("reason", "")

    def test_phase16_equip_checks_item_slot_mismatch(self):
        """Verify equip checks item slot matches requested slot."""
        inventory = InventoryState(owner_id="p1", items=[InventoryItem(item_id="helmet", quantity=1)])
        definitions = {
            "helmet": ItemDefinition(
                item_id="helmet",
                name="Helmet",
                equippable=True,
                slot="head",
            )
        }
        result = EquipmentManager.equip(inventory, "helmet", "main_hand", definitions)
        assert result["success"] is False
        assert "slot mismatch" in result.get("reason", "")

    def test_phase16_equip_without_definitions_works(self):
        """Verify equip works without definitions (backward compatibility)."""
        inventory = InventoryState(owner_id="p1", items=[InventoryItem(item_id="sword", quantity=1)])
        result = EquipmentManager.equip(inventory, "sword", "main_hand")
        assert result["success"] is True
        assert inventory.equipment["main_hand"] == "sword"