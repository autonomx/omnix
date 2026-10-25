from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict

from app.apps.rpg.rules.interactions.item_catalog import (
    definition_for_item_like,
)
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str


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

    container = _safe_dict(item.get("container") or definition.get("container"))
    if container:
        capacity = _safe_float(container.get("capacity_weight"), 0.0)
        contained_items = [
            normalize_item_instance(_safe_dict(contained))
            for contained in _safe_list(container.get("items"))
        ]
        normalized["container"] = {
            "capacity_weight": capacity,
            "items": contained_items,
        }

    repair = _safe_dict(item.get("repair") or definition.get("repair"))
    if repair:
        normalized["repair"] = deepcopy(repair)

    # Future item-system metadata. Preserve these now so later bundles do not
    # hit the same normalization-loss bug that repair metadata hit.
    consumable = _safe_dict(item.get("consumable") or definition.get("consumable"))
    if consumable:
        normalized["consumable"] = deepcopy(consumable)

    ammo = _safe_dict(item.get("ammo") or definition.get("ammo"))
    if ammo:
        normalized["ammo"] = deepcopy(ammo)

    crafting = _safe_dict(item.get("crafting") or definition.get("crafting"))
    if crafting:
        normalized["crafting"] = deepcopy(crafting)

    # Preserve lightweight custom state without allowing it to override normalized fields.
    for key in ("state", "metadata", "owner_id"):
        if key in item:
            normalized[key] = deepcopy(item[key])

    return normalized
