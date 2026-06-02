from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.currency import normalize_currency
from app.rpg.items.inventory_state import normalize_inventory_state

SOURCE = "deterministic_phase2_persistence_snapshot"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_item_quantities(inventory_state: Dict[str, Any]) -> Dict[str, int]:
    inventory_state = normalize_inventory_state(inventory_state)
    quantities: Dict[str, int] = {}
    for item in _safe_list(inventory_state.get("items")):
        item = _safe_dict(item)
        item_id = _safe_str(item.get("item_id"))
        if not item_id:
            continue
        quantities[item_id] = quantities.get(item_id, 0) + max(0, _safe_int(item.get("qty"), 0))
    return dict(sorted(quantities.items()))


def _merchant_transaction_summary(economy_state: Dict[str, Any]) -> Dict[str, Any]:
    merchants = _safe_dict(economy_state.get("merchants"))
    summary: Dict[str, Any] = {}
    for merchant_id, merchant in sorted(merchants.items(), key=lambda row: _safe_str(row[0])):
        merchant = _safe_dict(merchant)
        stock = {}
        for row in _safe_list(merchant.get("stock")):
            row = _safe_dict(row)
            item_id = _safe_str(row.get("item_id"))
            if item_id:
                stock[item_id] = max(0, _safe_int(row.get("qty"), 0))
        transaction_log = []
        for row in _safe_list(merchant.get("transaction_log")):
            row = _safe_dict(row)
            transaction_log.append(
                {
                    "kind": _safe_str(row.get("kind")),
                    "item_id": _safe_str(row.get("item_id")),
                    "qty": max(0, _safe_int(row.get("qty"), 0)),
                    "price": normalize_currency(row.get("price")),
                    "tick": max(0, _safe_int(row.get("tick"), 0)),
                    "reason": _safe_str(row.get("reason")),
                    "source": _safe_str(row.get("source")),
                }
            )
        summary[_safe_str(merchant_id)] = {
            "stock": dict(sorted(stock.items())),
            "currency": normalize_currency(merchant.get("currency")),
            "transaction_log": transaction_log[-50:],
            "source": _safe_str(merchant.get("source")),
        }
    return summary


def _service_log_summary(economy_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _safe_list(economy_state.get("service_transaction_log")):
        row = _safe_dict(row)
        rows.append(
            {
                "kind": _safe_str(row.get("kind")),
                "service_id": _safe_str(row.get("service_id")),
                "item_id": _safe_str(row.get("item_id")),
                "qty": max(0, _safe_int(row.get("qty"), 0)),
                "price": normalize_currency(row.get("price")),
                "tick": max(0, _safe_int(row.get("tick"), 0)),
                "reason": _safe_str(row.get("reason")),
                "source": _safe_str(row.get("source")),
            }
        )
    return rows[-50:]


def _survival_log_summary(economy_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _safe_list(economy_state.get("survival_log")):
        row = _safe_dict(row)
        rows.append(
            {
                "kind": _safe_str(row.get("kind")),
                "action_type": _safe_str(row.get("action_type")),
                "reason": _safe_str(row.get("reason")),
                "item_id": _safe_str(row.get("item_id")),
                "qty": max(0, _safe_int(row.get("qty"), 0)),
                "tick": max(0, _safe_int(row.get("tick"), 0)),
                "source": _safe_str(row.get("source")),
            }
        )
    return rows[-50:]


def build_phase2_persistence_snapshot(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact deterministic digest of Phase 2 persistence state."""
    state = _safe_dict(simulation_state)
    player_state = _safe_dict(state.get("player_state"))
    economy_state = _safe_dict(state.get("economy_state"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))
    rest_state = _safe_dict(player_state.get("rest_state"))
    survival_state = _safe_dict(player_state.get("survival_state"))

    return {
        "player_inventory": {
            "items": _normalize_item_quantities(inventory_state),
            "currency": normalize_currency(inventory_state.get("currency")),
            "capacity": max(0, _safe_int(inventory_state.get("capacity"), 0)),
        },
        "player_rest_state": deepcopy(rest_state),
        "player_survival_state": deepcopy(survival_state),
        "economy_state": {
            "merchants": _merchant_transaction_summary(economy_state),
            "service_transaction_log": _service_log_summary(economy_state),
            "survival_log": _survival_log_summary(economy_state),
        },
        "source": SOURCE,
    }
