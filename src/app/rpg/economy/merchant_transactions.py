from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.currency import (
    add_currency,
    can_afford,
    copper_to_currency,
    currency_to_copper_value,
    get_player_currency,
    normalize_currency,
    set_player_currency,
    subtract_currency_cost,
)
from app.rpg.items.inventory_state import (
    add_inventory_items,
    find_inventory_item,
    normalize_inventory_state,
    remove_inventory_item,
)
from app.rpg.items.item_registry import get_item_definition

SOURCE = "deterministic_merchant_transactions"

DEFAULT_MERCHANT_ID = "merchant:elara"
DEFAULT_MERCHANT_STOCK: List[Dict[str, Any]] = [
    {"item_id": "healing_potion", "qty": 3, "price": {"gold": 0, "silver": 10, "copper": 0}},
    {"item_id": "combat_knife", "qty": 2, "price": {"gold": 0, "silver": 10, "copper": 0}},
    {"item_id": "wooden_shield", "qty": 1, "price": {"gold": 0, "silver": 8, "copper": 0}},
]


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


def _stock_row(item_id: str, qty: int, price: Any) -> Dict[str, Any]:
    item_def = get_item_definition(item_id)
    return {
        "item_id": item_id,
        "qty": max(0, _safe_int(qty, 0)),
        "name": _safe_str(item_def.get("name") or item_id),
        "category": _safe_str(item_def.get("category")),
        "tags": list(_safe_list(item_def.get("tags")))[:8],
        "price": normalize_currency(price),
        "source": SOURCE,
    }


def build_default_merchant_stock() -> List[Dict[str, Any]]:
    return [
        _stock_row(
            _safe_str(row.get("item_id")),
            _safe_int(row.get("qty"), 0),
            row.get("price"),
        )
        for row in DEFAULT_MERCHANT_STOCK
    ]


def normalize_merchant_state(value: Any, *, merchant_id: str = DEFAULT_MERCHANT_ID) -> Dict[str, Any]:
    state = _safe_dict(value)
    stock_in = _safe_list(state.get("stock")) or build_default_merchant_stock()
    stock = []
    for row in stock_in:
        row = _safe_dict(row)
        item_id = _safe_str(row.get("item_id"))
        if not item_id:
            continue
        stock.append(_stock_row(item_id, _safe_int(row.get("qty"), 0), row.get("price")))

    return {
        "merchant_id": _safe_str(state.get("merchant_id") or merchant_id or DEFAULT_MERCHANT_ID),
        "stock": stock,
        "currency": normalize_currency(state.get("currency")),
        "transaction_log": list(_safe_list(state.get("transaction_log")))[-50:],
        "source": SOURCE,
    }


def ensure_merchant_state(
    simulation_state: Dict[str, Any],
    *,
    merchant_id: str = DEFAULT_MERCHANT_ID,
) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    economy_state = _safe_dict(state.get("economy_state"))
    merchants = _safe_dict(economy_state.get("merchants"))
    key = _safe_str(merchant_id or DEFAULT_MERCHANT_ID)
    merchants[key] = normalize_merchant_state(merchants.get(key), merchant_id=key)
    economy_state["merchants"] = merchants
    state["economy_state"] = economy_state
    return state


def get_merchant_state(simulation_state: Dict[str, Any], *, merchant_id: str = DEFAULT_MERCHANT_ID) -> Dict[str, Any]:
    state = ensure_merchant_state(simulation_state, merchant_id=merchant_id)
    economy_state = _safe_dict(state.get("economy_state"))
    merchants = _safe_dict(economy_state.get("merchants"))
    return normalize_merchant_state(merchants.get(_safe_str(merchant_id or DEFAULT_MERCHANT_ID)), merchant_id=merchant_id)


def _find_stock_entry(merchant_state: Dict[str, Any], item_id: str) -> Dict[str, Any]:
    item_id = _safe_str(item_id)
    for row in _safe_list(merchant_state.get("stock")):
        row = _safe_dict(row)
        if _safe_str(row.get("item_id")) == item_id:
            return row
    return {}


def _put_merchant_state(simulation_state: Dict[str, Any], merchant_state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    economy_state = _safe_dict(state.get("economy_state"))
    merchants = _safe_dict(economy_state.get("merchants"))
    merchant_state = normalize_merchant_state(merchant_state, merchant_id=_safe_str(merchant_state.get("merchant_id")))
    merchants[_safe_str(merchant_state.get("merchant_id"))] = merchant_state
    economy_state["merchants"] = merchants
    state["economy_state"] = economy_state
    return state


def buy_from_merchant(
    simulation_state: Dict[str, Any],
    *,
    item_id: str,
    qty: int = 1,
    merchant_id: str = DEFAULT_MERCHANT_ID,
    tick: int = 0,
) -> Dict[str, Any]:
    state = ensure_merchant_state(simulation_state, merchant_id=merchant_id)
    merchant_state = get_merchant_state(state, merchant_id=merchant_id)
    item_id = _safe_str(item_id)
    qty = max(1, _safe_int(qty, 1))
    stock_entry = _find_stock_entry(merchant_state, item_id)
    if not stock_entry:
        return _transaction_response("buy", False, "stock_item_not_found", state, merchant_state, item_id, qty, tick=tick)
    if _safe_int(stock_entry.get("qty"), 0) < qty:
        return _transaction_response("buy", False, "insufficient_stock", state, merchant_state, item_id, qty, tick=tick)

    unit_price = normalize_currency(stock_entry.get("price"))
    total_price = _multiply_currency(unit_price, qty)
    wallet = get_player_currency(state)
    if not can_afford(wallet, total_price):
        response = _transaction_response("buy", False, "insufficient_funds", state, merchant_state, item_id, qty, price=total_price, tick=tick)
        response["player_currency"] = wallet
        return response

    player_state = _safe_dict(state.get("player_state"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))
    inventory_state = add_inventory_items(inventory_state, [{"item_id": item_id, "qty": qty}])
    player_state["inventory_state"] = inventory_state
    state["player_state"] = player_state
    set_player_currency(state, subtract_currency_cost(wallet, total_price))

    stock_entry["qty"] = _safe_int(stock_entry.get("qty"), 0) - qty
    merchant_state["stock"] = [
        stock_entry if _safe_str(row.get("item_id")) == item_id else row
        for row in _safe_list(merchant_state.get("stock"))
    ]
    merchant_state["currency"] = add_currency(merchant_state.get("currency"), total_price)
    log_entry = _transaction_log_entry("buy", item_id, qty, total_price, tick=tick, reason="transaction_completed")
    merchant_state["transaction_log"] = list(_safe_list(merchant_state.get("transaction_log"))) + [log_entry]
    _put_merchant_state(state, merchant_state)

    return _transaction_response("buy", True, "transaction_completed", state, merchant_state, item_id, qty, price=total_price, log_entry=log_entry, tick=tick)


def sell_to_merchant(
    simulation_state: Dict[str, Any],
    *,
    item_id: str,
    qty: int = 1,
    merchant_id: str = DEFAULT_MERCHANT_ID,
    tick: int = 0,
) -> Dict[str, Any]:
    state = ensure_merchant_state(simulation_state, merchant_id=merchant_id)
    merchant_state = get_merchant_state(state, merchant_id=merchant_id)
    item_id = _safe_str(item_id)
    qty = max(1, _safe_int(qty, 1))
    player_state = _safe_dict(state.get("player_state"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))
    player_item = find_inventory_item(inventory_state, item_id)
    if not player_item or _safe_int(player_item.get("qty"), 0) < qty:
        return _transaction_response("sell", False, "player_item_not_found", state, merchant_state, item_id, qty, tick=tick)

    stock_entry = _find_stock_entry(merchant_state, item_id)
    unit_price = _sell_price_for_item(player_item, stock_entry)
    total_price = _multiply_currency(unit_price, qty)
    inventory_state = remove_inventory_item(inventory_state, item_id, qty)
    player_state["inventory_state"] = inventory_state
    state["player_state"] = player_state
    set_player_currency(state, add_currency(get_player_currency(state), total_price))

    if stock_entry:
        stock_entry["qty"] = _safe_int(stock_entry.get("qty"), 0) + qty
        merchant_state["stock"] = [
            stock_entry if _safe_str(row.get("item_id")) == item_id else row
            for row in _safe_list(merchant_state.get("stock"))
        ]
    else:
        merchant_state["stock"] = list(_safe_list(merchant_state.get("stock"))) + [_stock_row(item_id, qty, unit_price)]

    log_entry = _transaction_log_entry("sell", item_id, qty, total_price, tick=tick, reason="transaction_completed")
    merchant_state["transaction_log"] = list(_safe_list(merchant_state.get("transaction_log"))) + [log_entry]
    _put_merchant_state(state, merchant_state)

    return _transaction_response("sell", True, "transaction_completed", state, merchant_state, item_id, qty, price=total_price, log_entry=log_entry, tick=tick)


def _sell_price_for_item(player_item: Dict[str, Any], stock_entry: Dict[str, Any]) -> Dict[str, int]:
    if stock_entry:
        return _half_currency(stock_entry.get("price"))
    value = _safe_int(player_item.get("value"), 0)
    return copper_to_currency(max(1, value // 2))


def _multiply_currency(currency: Any, qty: int) -> Dict[str, int]:
    qty = max(1, _safe_int(qty, 1))
    return copper_to_currency(currency_to_copper_value(currency) * qty)


def _half_currency(currency: Any) -> Dict[str, int]:
    return copper_to_currency(max(1, currency_to_copper_value(currency) // 2))


def _transaction_log_entry(kind: str, item_id: str, qty: int, price: Any, *, tick: int, reason: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "item_id": item_id,
        "qty": qty,
        "price": normalize_currency(price),
        "tick": int(tick or 0),
        "reason": reason,
        "source": SOURCE,
    }


def _transaction_response(
    kind: str,
    resolved: bool,
    reason: str,
    simulation_state: Dict[str, Any],
    merchant_state: Dict[str, Any],
    item_id: str,
    qty: int,
    *,
    price: Any | None = None,
    log_entry: Dict[str, Any] | None = None,
    tick: int = 0,
) -> Dict[str, Any]:
    return {
        "resolved": resolved,
        "changed_state": bool(resolved),
        "action_type": kind,
        "reason": reason,
        "item_id": item_id,
        "qty": qty,
        "price": normalize_currency(price),
        "transaction_log_entry": deepcopy(_safe_dict(log_entry)),
        "merchant_state": deepcopy(normalize_merchant_state(merchant_state, merchant_id=_safe_str(merchant_state.get("merchant_id")))),
        "simulation_state": simulation_state,
        "tick": int(tick or 0),
        "source": SOURCE,
    }
