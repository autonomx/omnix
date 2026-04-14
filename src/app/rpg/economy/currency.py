from __future__ import annotations

from typing import Any, Dict


DENOMINATION_ORDER = ("gold", "silver", "copper")
DENOMINATION_VALUES = {
    "gold": 100,
    "silver": 10,
    "copper": 1,
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_currency(currency: Dict[str, Any] | None) -> Dict[str, int]:
    currency = _safe_dict(currency)
    gold = max(0, _safe_int(currency.get("gold", 0)))
    silver = max(0, _safe_int(currency.get("silver", 0)))
    copper = max(0, _safe_int(currency.get("copper", 0)))

    total_copper = (gold * 100) + (silver * 10) + copper
    return currency_from_copper(total_copper)


def currency_from_copper(total_copper: int) -> Dict[str, int]:
    total_copper = max(0, _safe_int(total_copper))
    gold = total_copper // 100
    remainder = total_copper % 100
    silver = remainder // 10
    copper = remainder % 10
    return {
        "gold": gold,
        "silver": silver,
        "copper": copper,
    }


def currency_to_copper_value(currency: Dict[str, Any] | None) -> int:
    normalized = normalize_currency(currency)
    return (
        int(normalized.get("gold", 0) or 0) * 100
        + int(normalized.get("silver", 0) or 0) * 10
        + int(normalized.get("copper", 0) or 0)
    )


def add_currency(
    currency: Dict[str, Any] | None,
    delta: Dict[str, Any] | None,
) -> Dict[str, int]:
    base_value = currency_to_copper_value(currency)
    delta_value = currency_to_copper_value(delta)
    return currency_from_copper(base_value + delta_value)


def can_afford(
    wallet: Dict[str, Any] | None,
    cost: Dict[str, Any] | None,
) -> bool:
    return currency_to_copper_value(wallet) >= currency_to_copper_value(cost)


def subtract_currency_cost(
    wallet: Dict[str, Any] | None,
    cost: Dict[str, Any] | None,
) -> Dict[str, int]:
    wallet_value = currency_to_copper_value(wallet)
    cost_value = currency_to_copper_value(cost)
    if cost_value > wallet_value:
        raise ValueError("insufficient currency")
    return currency_from_copper(wallet_value - cost_value)


def format_currency(currency: Dict[str, Any] | None) -> str:
    normalized = normalize_currency(currency)
    parts = []

    gold = int(normalized.get("gold", 0) or 0)
    silver = int(normalized.get("silver", 0) or 0)
    copper = int(normalized.get("copper", 0) or 0)

    if gold:
        parts.append(f"{gold}g")
    if silver:
        parts.append(f"{silver}s")
    if copper or not parts:
        parts.append(f"{copper}c")

    return " ".join(parts)


def currency_delta(before: Dict[str, Any] | None, after: Dict[str, Any] | None) -> Dict[str, int]:
    before_value = currency_to_copper_value(before)
    after_value = currency_to_copper_value(after)
    delta = after_value - before_value
    sign = -1 if delta < 0 else 1
    normalized = currency_from_copper(abs(delta))
    return {
        "gold": sign * normalized["gold"],
        "silver": sign * normalized["silver"],
        "copper": sign * normalized["copper"],
    }
