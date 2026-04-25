from __future__ import annotations

from typing import Any, Dict

Currency = Dict[str, int]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_currency(value: Any) -> Currency:
    value = _safe_dict(value)
    return {
        "gold": max(0, _safe_int(value.get("gold"), 0)),
        "silver": max(0, _safe_int(value.get("silver"), 0)),
        "copper": max(0, _safe_int(value.get("copper"), 0)),
    }


def normalize_delta_currency(value: Any) -> Currency:
    value = _safe_dict(value)
    return {
        "gold": _safe_int(value.get("gold"), 0),
        "silver": _safe_int(value.get("silver"), 0),
        "copper": _safe_int(value.get("copper"), 0),
    }


def currency_to_copper(value: Any) -> int:
    currency = normalize_delta_currency(value)
    return (
        currency["gold"] * 100
        + currency["silver"] * 10
        + currency["copper"]
    )


def copper_to_currency(total_copper: int) -> Currency:
    total = max(0, _safe_int(total_copper, 0))
    gold = total // 100
    total -= gold * 100
    silver = total // 10
    total -= silver * 10
    return {
        "gold": gold,
        "silver": silver,
        "copper": total,
    }


def can_afford(available: Any, price: Any) -> bool:
    return currency_to_copper(available) >= currency_to_copper(price)


def add_currency(left: Any, right: Any) -> Currency:
    left_total = currency_to_copper(left)
    right_total = currency_to_copper(right)
    return copper_to_currency(left_total + right_total)


def subtract_currency(left: Any, right: Any) -> Currency:
    left_total = currency_to_copper(left)
    right_total = currency_to_copper(right)
    return copper_to_currency(left_total - right_total)


def apply_currency_delta(current: Any, delta: Any) -> Currency:
    current_total = currency_to_copper(current)
    delta_total = currency_to_copper(delta)
    return copper_to_currency(current_total + delta_total)


def negative_currency(value: Any) -> Currency:
    currency = normalize_currency(value)
    return {
        "gold": -currency["gold"],
        "silver": -currency["silver"],
        "copper": -currency["copper"],
    }


def format_currency(value: Any) -> str:
    currency = normalize_currency(value)
    parts = []
    if currency["gold"]:
        parts.append(f"{currency['gold']} gold")
    if currency["silver"]:
        parts.append(f"{currency['silver']} silver")
    if currency["copper"]:
        parts.append(f"{currency['copper']} copper")
    return ", ".join(parts) if parts else "0 copper"


def get_player_currency(simulation_state: Dict[str, Any]) -> Currency:
    state = _safe_dict(simulation_state)

    player_state = _safe_dict(state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if inventory_state.get("currency") is not None:
        return normalize_currency(inventory_state.get("currency"))

    inventory_state = _safe_dict(state.get("inventory_state"))
    if inventory_state.get("currency") is not None:
        return normalize_currency(inventory_state.get("currency"))

    player_resources = _safe_dict(state.get("player_resources"))
    if player_resources.get("currency") is not None:
        return normalize_currency(player_resources.get("currency"))

    resources = _safe_dict(state.get("resources"))
    if resources.get("currency") is not None:
        return normalize_currency(resources.get("currency"))

    # Backward compatibility for older sessions that only stored gold.
    for source in (player_resources, resources, player_state, state):
        if source.get("gold") is not None:
            return normalize_currency({"gold": source.get("gold"), "silver": 0, "copper": 0})

    return normalize_currency({})


def set_player_currency(simulation_state: Dict[str, Any], currency: Any) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    player_state = _safe_dict(state.get("player_state"))
    if not player_state:
        player_state = {}
        state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {}
        player_state["inventory_state"] = inventory_state

    inventory_state["currency"] = normalize_currency(currency)
    return state


def currency_to_copper_value(currency: Any) -> int:
    return currency_to_copper(currency)


def currency_delta(before: Any, after: Any) -> Currency:
    before_value = currency_to_copper(before)
    after_value = currency_to_copper(after)
    delta = after_value - before_value
    sign = -1 if delta < 0 else 1
    normalized = copper_to_currency(abs(delta))
    return {
        "gold": sign * normalized["gold"],
        "silver": sign * normalized["silver"],
        "copper": sign * normalized["copper"],
    }


def subtract_currency_cost(wallet: Any, cost: Any) -> Currency:
    wallet_value = currency_to_copper(wallet)
    cost_value = currency_to_copper(cost)
    if cost_value > wallet_value:
        raise ValueError("insufficient currency")
    return copper_to_currency(wallet_value - cost_value)