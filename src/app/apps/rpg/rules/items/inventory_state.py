"""Phase 9.0 — Inventory state management.

Provides deterministic, serialisable inventory state with bounded capacity
and stack merging.
"""
from __future__ import annotations

from typing import Any, Dict

from app.apps.rpg.rules.economy.currency import normalize_currency

from .item_registry import get_item_definition
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict, list_copy as _safe_list, safe_str as _safe_str

_MAX_INVENTORY_SLOTS = 50
_MAX_LAST_LOOT = 10
_MAX_EQUIPMENT_SLOTS = 12


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

    result = {
        "item_id": item_id,
        "qty": qty,
        "name": _safe_str(item.get("name") or item_def.get("name")),
        "category": _safe_str(item.get("category") or item_def.get("category")),
        "tags": [str(tag) for tag in _safe_list(item.get("tags") or item_def.get("tags"))[:8]],
        "description": _safe_str(item.get("description") or item_def.get("description", "")),
        "value": _safe_int(item.get("value") or item_def.get("value"), 0),
        "durability": _safe_int(item.get("durability") or item_def.get("durability"), 100),
    }
    # Preserve instance_id for non-stackable items
    if item.get("instance_id"):
        result["instance_id"] = _safe_str(item["instance_id"])
    # Preserve combat_stats if present
    for field in ("combat_stats", "equipment", "quality"):
        val = item.get(field) or item_def.get(field)
        if isinstance(val, dict):
            result[field] = dict(val)
    return result


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

    currency = normalize_currency(_safe_dict(inventory_state.get("currency")))

    last_loot = []
    for item in _safe_list(inventory_state.get("last_loot"))[:_MAX_LAST_LOOT]:
        if isinstance(item, dict) and item.get("item_id"):
            last_loot.append(_normalize_stack(item))

    return {
        "items": items,
        "equipment": equipment_out,
        "capacity": max(0, _safe_int(inventory_state.get("capacity"), _MAX_INVENTORY_SLOTS)),
        "currency": currency,
        "last_loot": last_loot,
    }
