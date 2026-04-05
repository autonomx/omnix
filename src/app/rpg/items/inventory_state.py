"""Phase 9.0 — Inventory state management.

Provides deterministic, serialisable inventory state with bounded capacity
and stack merging.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .item_registry import get_item_definition


_MAX_INVENTORY_SLOTS = 50
_MAX_LAST_LOOT = 10
_MAX_EQUIPMENT_SLOTS = 12
_MAX_CURRENCY_KEYS = 8


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalize_stack(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return a clean, serialisable stack record."""
    item = _safe_dict(item)
    item_id = _safe_str(item.get("item_id"))
    qty = max(1, _safe_int(item.get("qty"), 1))
    item_def = get_item_definition(item_id)

    return {
        "item_id": item_id,
        "qty": qty,
        "name": _safe_str(item.get("name") or item_def.get("name")),
        "category": _safe_str(item.get("category") or item_def.get("category")),
        "tags": [str(tag) for tag in _safe_list(item.get("tags") or item_def.get("tags"))[:8]],
    }


def normalize_inventory_state(inventory_state: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitise and bound the full inventory state."""
    inventory_state = _safe_dict(inventory_state)

    items = []
    for item in _safe_list(inventory_state.get("items"))[:_MAX_INVENTORY_SLOTS]:
        if isinstance(item, dict) and item.get("item_id"):
            items.append(_normalize_stack(item))

    equipment_in = _safe_dict(inventory_state.get("equipment"))
    equipment_out: Dict[str, Dict[str, Any]] = {}
    for slot_name in sorted(equipment_in.keys())[:_MAX_EQUIPMENT_SLOTS]:
        slot_value = equipment_in.get(slot_name)
        if isinstance(slot_value, dict) and slot_value.get("item_id"):
            equipment_out[str(slot_name)] = _normalize_stack(slot_value)

    currency_in = _safe_dict(inventory_state.get("currency"))
    currency_out: Dict[str, int] = {}
    for key in sorted(currency_in.keys())[:_MAX_CURRENCY_KEYS]:
        currency_out[str(key)] = max(0, _safe_int(currency_in.get(key), 0))

    last_loot = []
    for item in _safe_list(inventory_state.get("last_loot"))[:_MAX_LAST_LOOT]:
        if isinstance(item, dict) and item.get("item_id"):
            last_loot.append(_normalize_stack(item))

    return {
        "items": items,
        "equipment": equipment_out,
        "capacity": max(0, _safe_int(inventory_state.get("capacity"), _MAX_INVENTORY_SLOTS)),
        "currency": currency_out,
        "last_loot": last_loot,
    }


def ensure_inventory_state(player_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure *player_state* has a well-formed ``inventory_state`` subtree."""
    player_state = _safe_dict(player_state)
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))
    if not inventory_state.get("capacity"):
        inventory_state["capacity"] = _MAX_INVENTORY_SLOTS
    player_state["inventory_state"] = inventory_state
    return player_state


def _merge_stack(items: List[Dict[str, Any]], incoming: Dict[str, Any], capacity: int) -> List[Dict[str, Any]]:
    """Merge *incoming* into *items*, stacking if possible, respecting *capacity*."""
    incoming = _normalize_stack(incoming)
    if not incoming.get("item_id"):
        return items

    item_def = get_item_definition(incoming.get("item_id"))
    if item_def.get("stackable"):
        for idx, existing in enumerate(items):
            if _safe_str(existing.get("item_id")) == incoming["item_id"]:
                merged = dict(existing)
                merged["qty"] = _safe_int(existing.get("qty"), 1) + _safe_int(incoming.get("qty"), 1)
                items[idx] = _normalize_stack(merged)
                return items

    if len(items) >= capacity:
        return items

    items.append(incoming)
    return items


def add_inventory_items(inventory_state: Dict[str, Any], incoming_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add *incoming_items* to the inventory, merging stacks where possible."""
    inventory_state = normalize_inventory_state(inventory_state)
    capacity = max(0, _safe_int(inventory_state.get("capacity"), _MAX_INVENTORY_SLOTS))
    items = list(inventory_state.get("items") or [])

    for item in _safe_list(incoming_items):
        if isinstance(item, dict):
            items = _merge_stack(items, item, capacity)

    inventory_state["items"] = items[:capacity]
    return inventory_state


def remove_inventory_item(inventory_state: Dict[str, Any], item_id: str, qty: int = 1) -> Dict[str, Any]:
    """Remove up to *qty* of *item_id* from inventory."""
    inventory_state = normalize_inventory_state(inventory_state)
    item_id = _safe_str(item_id)
    qty = max(1, _safe_int(qty, 1))

    items_out: List[Dict[str, Any]] = []
    remaining_to_remove = qty

    for item in _safe_list(inventory_state.get("items")):
        current = _normalize_stack(item)
        if current.get("item_id") != item_id or remaining_to_remove <= 0:
            items_out.append(current)
            continue

        current_qty = _safe_int(current.get("qty"), 1)
        if current_qty > remaining_to_remove:
            current["qty"] = current_qty - remaining_to_remove
            items_out.append(current)
            remaining_to_remove = 0
        else:
            remaining_to_remove -= current_qty

    inventory_state["items"] = items_out
    return inventory_state


def record_inventory_loot(inventory_state: Dict[str, Any], loot_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add *loot_items* and record them as ``last_loot``."""
    inventory_state = add_inventory_items(inventory_state, loot_items)
    inventory_state["last_loot"] = [
        _normalize_stack(item)
        for item in _safe_list(loot_items)[:_MAX_LAST_LOOT]
        if isinstance(item, dict) and item.get("item_id")
    ]
    return inventory_state


def build_inventory_summary(inventory_state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact summary of the current inventory."""
    inventory_state = normalize_inventory_state(inventory_state)
    items = _safe_list(inventory_state.get("items"))
    total_item_kinds = len(items)
    total_item_qty = sum(max(0, _safe_int(item.get("qty"), 0)) for item in items if isinstance(item, dict))
    return {
        "slots_used": total_item_kinds,
        "capacity": max(0, _safe_int(inventory_state.get("capacity"), _MAX_INVENTORY_SLOTS)),
        "total_item_qty": total_item_qty,
        "last_loot_count": len(_safe_list(inventory_state.get("last_loot"))),
    }