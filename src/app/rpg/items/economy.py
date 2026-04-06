"""Phase 16 — Inventory / equipment / economy expansion.

Item schemas, equipment slots, consumables, loot generation,
shops/barter, item effects, UI bridge, migration, determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_INVENTORY_SLOTS = 50
MAX_EQUIPMENT_SLOTS = 12
MAX_SHOP_ITEMS = 30
MAX_STACK = 99
EQUIPMENT_SLOT_NAMES = (
    "head", "chest", "legs", "feet", "hands",
    "main_hand", "off_hand", "ring_1", "ring_2",
    "neck", "back", "belt",
)
ITEM_RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
ITEM_CATEGORIES = ("weapon", "armor", "consumable", "material", "quest", "currency", "utility")

# ---------------------------------------------------------------------------
# 16.0 — Item schema foundations
# ---------------------------------------------------------------------------

@dataclass
class ItemDefinition:
    item_id: str = ""
    name: str = ""
    category: str = "material"
    rarity: str = "common"
    description: str = ""
    base_value: int = 0
    stackable: bool = True
    max_stack: int = MAX_STACK
    equippable: bool = False
    slot: str = ""
    effects: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id, "name": self.name,
            "category": self.category, "rarity": self.rarity,
            "description": self.description, "base_value": self.base_value,
            "stackable": self.stackable, "max_stack": self.max_stack,
            "equippable": self.equippable, "slot": self.slot,
            "effects": list(self.effects),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ItemDefinition":
        return cls(
            item_id=_ss(d.get("item_id")), name=_ss(d.get("name")),
            category=_ss(d.get("category"), "material"),
            rarity=_ss(d.get("rarity"), "common"),
            description=_ss(d.get("description")),
            base_value=max(0, _si(d.get("base_value"))),
            stackable=bool(d.get("stackable", True)),
            max_stack=max(1, _si(d.get("max_stack"), MAX_STACK)),
            equippable=bool(d.get("equippable", False)),
            slot=_ss(d.get("slot")),
            effects=list(d.get("effects") or []),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class InventoryItem:
    item_id: str = ""
    quantity: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id, "quantity": self.quantity,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InventoryItem":
        return cls(
            item_id=_ss(d.get("item_id")),
            quantity=max(0, _si(d.get("quantity"), 1)),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class InventoryState:
    owner_id: str = ""
    items: List[InventoryItem] = field(default_factory=list)
    equipment: Dict[str, str] = field(default_factory=dict)  # slot -> item_id
    currency: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "items": [i.to_dict() for i in self.items],
            "equipment": dict(self.equipment),
            "currency": dict(self.currency),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InventoryState":
        return cls(
            owner_id=_ss(d.get("owner_id")),
            items=[InventoryItem.from_dict(i) for i in (d.get("items") or [])],
            equipment=dict(d.get("equipment") or {}),
            currency=dict(d.get("currency") or {}),
        )


# ---------------------------------------------------------------------------
# 16.1 — Equipment / slots / loadout
# ---------------------------------------------------------------------------

class EquipmentManager:
    """Manage equipment slots."""

    @staticmethod
    def equip(inventory: InventoryState, item_id: str, slot: str) -> Dict[str, Any]:
        if slot not in EQUIPMENT_SLOT_NAMES:
            return {"success": False, "reason": f"invalid slot: {slot}"}
        previous = inventory.equipment.get(slot)
        inventory.equipment[slot] = item_id
        return {"success": True, "previous_item": previous, "slot": slot}

    @staticmethod
    def unequip(inventory: InventoryState, slot: str) -> Dict[str, Any]:
        if slot not in inventory.equipment:
            return {"success": False, "reason": "slot empty"}
        item_id = inventory.equipment.pop(slot)
        return {"success": True, "item_id": item_id, "slot": slot}

    @staticmethod
    def get_loadout(inventory: InventoryState) -> Dict[str, str]:
        return dict(inventory.equipment)

    @staticmethod
    def is_slot_occupied(inventory: InventoryState, slot: str) -> bool:
        return slot in inventory.equipment


# ---------------------------------------------------------------------------
# 16.2 — Consumables / utility items
# ---------------------------------------------------------------------------

class ConsumableManager:
    """Handle consumable items."""

    @staticmethod
    def use_consumable(inventory: InventoryState, item_id: str) -> Dict[str, Any]:
        for item in inventory.items:
            if item.item_id == item_id and item.quantity > 0:
                item.quantity -= 1
                if item.quantity <= 0:
                    inventory.items = [i for i in inventory.items if i.quantity > 0]
                return {"success": True, "item_id": item_id, "remaining": item.quantity}
        return {"success": False, "reason": "item not found or out of stock"}

    @staticmethod
    def add_item(inventory: InventoryState, item_id: str,
                 quantity: int = 1) -> Dict[str, Any]:
        for item in inventory.items:
            if item.item_id == item_id:
                item.quantity = min(item.quantity + quantity, MAX_STACK)
                return {"success": True, "total": item.quantity}
        if len(inventory.items) >= MAX_INVENTORY_SLOTS:
            return {"success": False, "reason": "inventory full"}
        inventory.items.append(InventoryItem(item_id=item_id, quantity=min(quantity, MAX_STACK)))
        return {"success": True, "total": min(quantity, MAX_STACK)}

    @staticmethod
    def remove_item(inventory: InventoryState, item_id: str,
                    quantity: int = 1) -> Dict[str, Any]:
        for item in inventory.items:
            if item.item_id == item_id:
                if item.quantity < quantity:
                    return {"success": False, "reason": "insufficient quantity"}
                item.quantity -= quantity
                if item.quantity <= 0:
                    inventory.items = [i for i in inventory.items if i.quantity > 0]
                return {"success": True, "removed": quantity}
        return {"success": False, "reason": "item not found"}


# ---------------------------------------------------------------------------
# 16.3 — Loot generation / discovery rules
# ---------------------------------------------------------------------------

class LootGenerator:
    """Deterministic loot generation."""

    LOOT_TABLES: Dict[str, List[Dict[str, Any]]] = {
        "common_enemy": [
            {"item_id": "gold_coin", "quantity": 5, "weight": 0.8},
            {"item_id": "healing_potion", "quantity": 1, "weight": 0.3},
        ],
        "rare_enemy": [
            {"item_id": "gold_coin", "quantity": 20, "weight": 0.9},
            {"item_id": "healing_potion", "quantity": 2, "weight": 0.5},
            {"item_id": "iron_sword", "quantity": 1, "weight": 0.2},
        ],
        "chest": [
            {"item_id": "gold_coin", "quantity": 50, "weight": 0.7},
            {"item_id": "healing_potion", "quantity": 3, "weight": 0.4},
        ],
    }

    @classmethod
    def generate_loot(cls, table_id: str, luck_modifier: float = 0.0) -> List[Dict[str, Any]]:
        table = cls.LOOT_TABLES.get(table_id, [])
        result: List[Dict[str, Any]] = []
        for entry in table:
            threshold = entry.get("weight", 0.5) + _clamp(luck_modifier, -0.5, 0.5)
            if threshold >= 0.5:
                result.append({
                    "item_id": entry["item_id"],
                    "quantity": entry.get("quantity", 1),
                })
        return result


# ---------------------------------------------------------------------------
# 16.4 — Shops / barter / economy
# ---------------------------------------------------------------------------

@dataclass
class ShopState:
    shop_id: str = ""
    owner_id: str = ""
    inventory: List[Dict[str, Any]] = field(default_factory=list)
    buy_modifier: float = 1.0   # multiplier for buy prices
    sell_modifier: float = 0.5  # multiplier for sell prices

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shop_id": self.shop_id, "owner_id": self.owner_id,
            "inventory": list(self.inventory),
            "buy_modifier": self.buy_modifier,
            "sell_modifier": self.sell_modifier,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ShopState":
        return cls(
            shop_id=_ss(d.get("shop_id")),
            owner_id=_ss(d.get("owner_id")),
            inventory=list(d.get("inventory") or []),
            buy_modifier=_sf(d.get("buy_modifier"), 1.0),
            sell_modifier=_sf(d.get("sell_modifier"), 0.5),
        )


class ShopManager:
    """Handle shop transactions."""

    @staticmethod
    def buy_item(player_inv: InventoryState, shop: ShopState,
                 item_id: str, base_value: int) -> Dict[str, Any]:
        cost = int(base_value * shop.buy_modifier)
        gold = player_inv.currency.get("gold", 0)
        if gold < cost:
            return {"success": False, "reason": "insufficient gold"}

        result = ConsumableManager.add_item(player_inv, item_id, 1)
        if not result.get("success"):
            return result

        player_inv.currency["gold"] = gold - cost
        return {"success": True, "item_id": item_id, "cost": cost}

    @staticmethod
    def sell_item(player_inv: InventoryState, shop: ShopState,
                  item_id: str, base_value: int) -> Dict[str, Any]:
        result = ConsumableManager.remove_item(player_inv, item_id, 1)
        if not result.get("success"):
            return result

        value = int(base_value * shop.sell_modifier)
        player_inv.currency["gold"] = player_inv.currency.get("gold", 0) + value
        return {"success": True, "item_id": item_id, "value": value}


# ---------------------------------------------------------------------------
# 16.5 — Item effects into simulation / encounters
# ---------------------------------------------------------------------------

class ItemEffectEngine:
    """Apply item effects to simulation and encounters."""

    @staticmethod
    def apply_item_effects(effects: List[Dict[str, Any]],
                           target_state: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(target_state)
        applied: List[str] = []
        for eff in effects:
            etype = _ss(eff.get("type"))
            value = _sf(eff.get("value"))
            if etype == "restore_hp":
                result["hp"] = min(
                    _sf(result.get("max_hp"), 100),
                    _sf(result.get("hp"), 100) + value,
                )
                applied.append(f"restore_hp:{value}")
            elif etype == "buff_attack":
                result["attack_bonus"] = _sf(result.get("attack_bonus")) + value
                applied.append(f"buff_attack:{value}")
            elif etype == "buff_defense":
                result["defense_bonus"] = _sf(result.get("defense_bonus")) + value
                applied.append(f"buff_defense:{value}")
            elif etype == "restore_resource":
                result["resource"] = min(
                    _sf(result.get("max_resource"), 100),
                    _sf(result.get("resource"), 100) + value,
                )
                applied.append(f"restore_resource:{value}")
        result["applied_effects"] = applied
        return result


# ---------------------------------------------------------------------------
# 16.6 — Inventory UI / presentation
# ---------------------------------------------------------------------------

class InventoryPresenter:
    """Format inventory for UI."""

    @staticmethod
    def present_inventory(inventory: InventoryState) -> Dict[str, Any]:
        return {
            "owner_id": inventory.owner_id,
            "slot_count": len(inventory.items),
            "max_slots": MAX_INVENTORY_SLOTS,
            "items": [i.to_dict() for i in inventory.items],
            "equipment": dict(inventory.equipment),
            "currency": dict(inventory.currency),
        }

    @staticmethod
    def present_shop(shop: ShopState) -> Dict[str, Any]:
        return {
            "shop_id": shop.shop_id,
            "owner_id": shop.owner_id,
            "item_count": len(shop.inventory),
            "buy_modifier": shop.buy_modifier,
            "sell_modifier": shop.sell_modifier,
            "items": list(shop.inventory),
        }


# ---------------------------------------------------------------------------
# 16.7 — Inventory migration / compatibility
# ---------------------------------------------------------------------------

class InventoryMigrator:
    """Migrate old inventory formats."""

    @staticmethod
    def migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add equipment and currency to old format."""
        result = dict(data)
        if "equipment" not in result:
            result["equipment"] = {}
        if "currency" not in result:
            result["currency"] = {"gold": 0}
        if "items" in result:
            for item in result["items"]:
                if "metadata" not in item:
                    item["metadata"] = {}
        result["_version"] = 2
        return result

    @staticmethod
    def is_current_version(data: Dict[str, Any]) -> bool:
        return data.get("_version", 1) >= 2


# ---------------------------------------------------------------------------
# 16.8 — Inventory determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class InventoryDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: InventoryState, s2: InventoryState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(inventory: InventoryState) -> List[str]:
        violations: List[str] = []
        if len(inventory.items) > MAX_INVENTORY_SLOTS:
            violations.append(f"items exceed max ({len(inventory.items)} > {MAX_INVENTORY_SLOTS})")
        for slot in inventory.equipment:
            if slot not in EQUIPMENT_SLOT_NAMES:
                violations.append(f"invalid equipment slot: {slot}")
        for item in inventory.items:
            if item.quantity > MAX_STACK:
                violations.append(f"item {item.item_id} exceeds max stack ({item.quantity} > {MAX_STACK})")
            if item.quantity < 0:
                violations.append(f"item {item.item_id} negative quantity: {item.quantity}")
        return violations

    @staticmethod
    def normalize_state(inventory: InventoryState) -> InventoryState:
        items = [i for i in inventory.items if i.quantity > 0]
        for i in items:
            i.quantity = min(i.quantity, MAX_STACK)
        if len(items) > MAX_INVENTORY_SLOTS:
            items = items[:MAX_INVENTORY_SLOTS]
        equipment = {k: v for k, v in inventory.equipment.items()
                     if k in EQUIPMENT_SLOT_NAMES}
        return InventoryState(
            owner_id=inventory.owner_id,
            items=items, equipment=equipment,
            currency=dict(inventory.currency),
        )
