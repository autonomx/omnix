from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.interactions.item_catalog import (
    definition_for_item_like,
    get_item_definition,
)

DEFAULT_CARRY_CAPACITY = 50.0


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _slug(value: str) -> str:
    value = _safe_str(value).strip().lower()
    value = re.sub(r"[^a-z0-9:_-]+", "_", value)
    value = value.strip("_") or "unknown"
    return value


def item_id_for_definition(definition_id: str) -> str:
    clean = _safe_str(definition_id).replace("def:", "")
    return f"item:{_slug(clean)}"


def normalize_currency_value(value: Any) -> Dict[str, int]:
    value = _safe_dict(value)
    return {
        "gold": max(0, _safe_int(value.get("gold"), 0)),
        "silver": max(0, _safe_int(value.get("silver"), 0)),
        "copper": max(0, _safe_int(value.get("copper"), 0)),
    }


def normalize_item_instance(item: Dict[str, Any]) -> Dict[str, Any]:
    item = deepcopy(_safe_dict(item))
    definition = definition_for_item_like(item)

    definition_id = (
        _safe_str(item.get("definition_id"))
        or _safe_str(definition.get("definition_id"))
    )

    name = (
        _safe_str(item.get("name"))
        or _safe_str(definition.get("name"))
        or definition_id.replace("def:", "").replace("_", " ")
        or _safe_str(item.get("item_id")).replace("item:", "").replace("_", " ")
        or "unknown item"
    )

    item_id = (
        _safe_str(item.get("item_id"))
        or _safe_str(item.get("id"))
        or _safe_str(item.get("entity_id"))
        or item_id_for_definition(definition_id)
    )

    stackable = bool(item.get("stackable", definition.get("stackable", False)))
    max_stack = max(1, _safe_int(item.get("max_stack", definition.get("max_stack", 99 if stackable else 1)), 1))
    quantity = max(1, _safe_int(item.get("quantity"), 1))
    if not stackable:
        quantity = 1
        max_stack = 1

    unit_weight = max(0.0, _safe_float(item.get("unit_weight", definition.get("unit_weight", 0.0)), 0.0))
    total_weight = round(unit_weight * quantity, 4)

    normalized = {
        "item_id": item_id,
        "definition_id": definition_id or item_id.replace("item:", "def:"),
        "name": name,
        "kind": _safe_str(item.get("kind") or item.get("item_type") or item.get("type") or definition.get("kind")),
        "quantity": quantity,
        "stackable": stackable,
        "max_stack": max_stack,
        "unit_weight": unit_weight,
        "total_weight": total_weight,
        "rarity": _safe_str(item.get("rarity") or definition.get("rarity") or "common"),
        "value": normalize_currency_value(item.get("value") or definition.get("value")),
        "tags": _safe_list(item.get("tags") or definition.get("tags")),
        "aliases": _safe_list(item.get("aliases")),
        "source": _safe_str(item.get("source") or "deterministic_item_model"),
    }

    if "location_id" in item:
        normalized["location_id"] = _safe_str(item.get("location_id"))

    equipment = _safe_dict(item.get("equipment") or definition.get("equipment"))
    if equipment:
        normalized["equipment"] = deepcopy(equipment)
        if _safe_str(equipment.get("slot")):
            normalized["slot"] = _safe_str(equipment.get("slot"))

    if _safe_str(item.get("slot")):
        normalized["slot"] = _safe_str(item.get("slot"))

    condition = _safe_dict(item.get("condition") or definition.get("condition"))
    if condition:
        normalized["condition"] = {
            "durability": max(0.0, min(1.0, _safe_float(condition.get("durability"), 1.0))),
            "max_durability": max(0.0, _safe_float(condition.get("max_durability"), 1.0)),
        }

    # Preserve lightweight custom state without allowing it to override normalized fields.
    for key in ("state", "metadata", "owner_id"):
        if key in item:
            normalized[key] = deepcopy(item[key])

    return normalized


def split_stack(item: Dict[str, Any], quantity: int) -> tuple[Dict[str, Any], Dict[str, Any]]:
    item = normalize_item_instance(item)
    quantity = max(0, min(_safe_int(quantity, 0), _safe_int(item.get("quantity"), 1)))

    taken = deepcopy(item)
    remaining = deepcopy(item)

    taken["quantity"] = quantity
    taken["total_weight"] = round(_safe_float(taken.get("unit_weight"), 0.0) * quantity, 4)

    remaining_qty = _safe_int(item.get("quantity"), 1) - quantity
    remaining["quantity"] = remaining_qty
    remaining["total_weight"] = round(_safe_float(remaining.get("unit_weight"), 0.0) * remaining_qty, 4)

    return taken, remaining


def can_stack_items(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    a = normalize_item_instance(a)
    b = normalize_item_instance(b)

    return (
        bool(a.get("stackable"))
        and bool(b.get("stackable"))
        and _safe_str(a.get("definition_id")) == _safe_str(b.get("definition_id"))
        and _safe_str(a.get("rarity")) == _safe_str(b.get("rarity"))
    )


def add_item_to_items_list(items: List[Any], item: Dict[str, Any]) -> Dict[str, Any]:
    """Add item, stacking when possible.

    Returns a result with updated items and stack/add details.
    """
    normalized_items = [normalize_item_instance(_safe_dict(existing)) for existing in _safe_list(items)]
    incoming = normalize_item_instance(item)
    remaining_qty = _safe_int(incoming.get("quantity"), 1)
    stack_events = []

    if incoming.get("stackable"):
        for existing in normalized_items:
            if remaining_qty <= 0:
                break
            if not can_stack_items(existing, incoming):
                continue

            max_stack = _safe_int(existing.get("max_stack"), 1)
            current_qty = _safe_int(existing.get("quantity"), 1)
            room = max(0, max_stack - current_qty)
            if room <= 0:
                continue

            moved = min(room, remaining_qty)
            existing["quantity"] = current_qty + moved
            existing["total_weight"] = round(_safe_float(existing.get("unit_weight"), 0.0) * _safe_int(existing.get("quantity"), 1), 4)
            remaining_qty -= moved
            stack_events.append({
                "target_item_id": _safe_str(existing.get("item_id")),
                "quantity_added": moved,
                "quantity_after": existing["quantity"],
            })

    added_items = []
    while remaining_qty > 0:
        new_item = deepcopy(incoming)
        new_qty = min(remaining_qty, _safe_int(new_item.get("max_stack"), 1))
        new_item["quantity"] = new_qty
        new_item["total_weight"] = round(_safe_float(new_item.get("unit_weight"), 0.0) * new_qty, 4)

        # Avoid duplicate IDs for overflow stacks.
        if any(_safe_str(existing.get("item_id")) == _safe_str(new_item.get("item_id")) for existing in normalized_items):
            suffix = len(normalized_items) + len(added_items) + 1
            new_item["item_id"] = f"{_safe_str(new_item.get('item_id'))}:{suffix}"

        normalized_items.append(new_item)
        added_items.append(deepcopy(new_item))
        remaining_qty -= new_qty

    return {
        "items": normalized_items,
        "stacked": bool(stack_events),
        "stack_events": stack_events,
        "added_items": added_items,
        "incoming_item": incoming,
        "source": "deterministic_item_model",
    }


def calculate_inventory_weight(items: List[Any]) -> float:
    total = 0.0
    for item in _safe_list(items):
        normalized = normalize_item_instance(_safe_dict(item))
        total += _safe_float(normalized.get("total_weight"), 0.0)
    return round(total, 4)


def encumbrance_state_for_weight(weight: float, capacity: float) -> str:
    capacity = max(0.01, _safe_float(capacity, DEFAULT_CARRY_CAPACITY))
    ratio = _safe_float(weight, 0.0) / capacity

    if ratio > 1.5:
        return "immobile"
    if ratio > 1.0:
        return "overloaded"
    if ratio > 0.7:
        return "burdened"
    return "normal"


def recalculate_inventory_derived_fields(inventory: Dict[str, Any]) -> Dict[str, Any]:
    inventory = deepcopy(_safe_dict(inventory))
    items = [normalize_item_instance(_safe_dict(item)) for item in _safe_list(inventory.get("items"))]
    inventory["items"] = items

    if not isinstance(inventory.get("equipment"), dict):
        inventory["equipment"] = {}

    capacity = _safe_float(inventory.get("carry_capacity"), DEFAULT_CARRY_CAPACITY)
    weight = calculate_inventory_weight(items)

    inventory["carry_capacity"] = capacity
    inventory["carry_weight"] = weight
    inventory["encumbrance_state"] = encumbrance_state_for_weight(weight, capacity)
    inventory["source"] = _safe_str(inventory.get("source") or "deterministic_item_model")
    return inventory
