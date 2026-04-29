from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.interactions.item_model import (
    add_item_to_items_list,
    normalize_item_instance,
    recalculate_inventory_derived_fields,
)
from app.rpg.interactions.loot_catalog import get_loot_table


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


def _deterministic_int(seed: str, *, modulo: int) -> int:
    modulo = max(1, int(modulo))
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % modulo


def _weighted_choice(options: List[Dict[str, Any]], *, seed: str) -> Dict[str, Any]:
    clean = [_safe_dict(option) for option in options if _safe_int(_safe_dict(option).get("weight"), 0) > 0]
    if not clean:
        return {}

    total = sum(_safe_int(option.get("weight"), 0) for option in clean)
    cursor = _deterministic_int(seed, modulo=total)

    running = 0
    for option in clean:
        running += _safe_int(option.get("weight"), 0)
        if cursor < running:
            return deepcopy(option)

    return deepcopy(clean[-1])


def _quantity_for_roll(roll: Dict[str, Any], *, seed: str) -> int:
    q_min = _safe_int(roll.get("quantity_min"), 1)
    q_max = max(q_min, _safe_int(roll.get("quantity_max"), q_min))
    return q_min + _deterministic_int(seed, modulo=(q_max - q_min + 1))


def _player_inventory(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    inv = _safe_dict(player_state.get("inventory"))
    if not isinstance(inv.get("items"), list):
        inv["items"] = []
    if not isinstance(inv.get("equipment"), dict):
        inv["equipment"] = {}
    player_state["inventory"] = inv
    simulation_state["player_state"] = player_state
    return inv


def generate_loot_from_table(
    simulation_state: Dict[str, Any],
    *,
    loot_table_id: str,
    source_id: str = "",
    session_id: str = "",
    tick: int = 0,
    add_to_inventory: bool = True,
) -> Dict[str, Any]:
    table = get_loot_table(loot_table_id)
    if not table:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "loot_table_not_found",
            "loot_table_id": loot_table_id,
            "source": "deterministic_loot_runtime",
        }

    rolls = _safe_list(table.get("rolls"))
    roll_count = max(1, _safe_int(table.get("roll_count"), 1))
    seed_base = f"{session_id}|{loot_table_id}|{source_id}|{tick}"

    created = []
    add_result: Dict[str, Any] = {}

    inventory = _player_inventory(simulation_state) if add_to_inventory else {}

    for idx in range(roll_count):
        roll = _weighted_choice(rolls, seed=f"{seed_base}|roll|{idx}")
        if not roll:
            continue

        quantity = _quantity_for_roll(roll, seed=f"{seed_base}|qty|{idx}")
        item = normalize_item_instance({
            "definition_id": _safe_str(roll.get("definition_id")),
            "quantity": quantity,
            "source": "deterministic_loot_runtime",
        })

        created.append({
            "definition_id": _safe_str(item.get("definition_id")),
            "quantity": quantity,
            "item": deepcopy(item),
        })

        if add_to_inventory:
            add_result = add_item_to_items_list(_safe_list(inventory.get("items")), item)
            inventory["items"] = _safe_list(add_result.get("items"))

    if add_to_inventory:
        inventory = recalculate_inventory_derived_fields(inventory)
        simulation_state["player_state"]["inventory"] = inventory

    return {
        "resolved": True,
        "changed_state": bool(add_to_inventory and created),
        "reason": "loot_generated",
        "loot_table_id": loot_table_id,
        "source_id": source_id,
        "session_id": session_id,
        "tick": int(tick or 0),
        "items_created": created,
        "added_to_inventory": bool(add_to_inventory),
        "carry_weight": inventory.get("carry_weight") if inventory else 0,
        "encumbrance_state": inventory.get("encumbrance_state") if inventory else "",
        "source": "deterministic_loot_runtime",
    }
