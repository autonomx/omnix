"""Phase 9.0 — Item effect hooks.

Applies deterministic item effects to simulation state.
"""
from __future__ import annotations

from typing import Any, Dict

from .inventory_state import normalize_inventory_state, remove_inventory_item
from .item_registry import get_item_definition


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def apply_item_use(simulation_state: Dict[str, Any], item_id: str) -> Dict[str, Any]:
    """Apply a single item use, consuming it from inventory and returning effect result.

    Returns a dict with keys:
        - simulation_state: updated state
        - result: {ok, item_id, effect?, reason?}
    """
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))
    item_id = _safe_str(item_id)
    item_def = get_item_definition(item_id)

    if not item_def:
        return {
            "simulation_state": simulation_state,
            "result": {
                "ok": False,
                "reason": "unknown_item",
                "item_id": item_id,
            },
        }

    has_item = any(
        isinstance(item, dict)
        and _safe_str(item.get("item_id")) == item_id
        and _safe_int(item.get("qty"), 0) > 0
        for item in (inventory_state.get("items") or [])
    )
    if not has_item:
        return {
            "simulation_state": simulation_state,
            "result": {
                "ok": False,
                "reason": "item_not_owned",
                "item_id": item_id,
            },
        }

    effect = _safe_dict(item_def.get("effect"))
    inventory_state = remove_inventory_item(inventory_state, item_id, qty=1)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state

    return {
        "simulation_state": simulation_state,
        "result": {
            "ok": True,
            "item_id": item_id,
            "effect": effect,
        },
    }