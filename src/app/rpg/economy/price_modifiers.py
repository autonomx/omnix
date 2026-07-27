from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.currency import copper_to_currency, currency_to_copper_value, normalize_currency

SOURCE = "deterministic_price_modifiers"

MIN_PRICE_COPPER = 1
MIN_BUY_MULTIPLIER_BPS = 6500
MAX_BUY_MULTIPLIER_BPS = 15000
MIN_SELL_MULTIPLIER_BPS = 6500
MAX_SELL_MULTIPLIER_BPS = 15000
DEFAULT_SELL_MULTIPLIER_BPS = 10000


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


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _relationship_value(player_state: Dict[str, Any], merchant_id: str) -> int:
    relationships = _safe_dict(player_state.get("relationships"))
    candidates = [merchant_id]
    if merchant_id.startswith("merchant:"):
        candidates.append(merchant_id.split(":", 1)[1])
    for candidate in candidates:
        row = _safe_dict(relationships.get(candidate))
        if row:
            return _safe_int(row.get("score", row.get("value", 0)), 0)
    return 0


def _reputation_value(player_state: Dict[str, Any], merchant_id: str) -> int:
    reputation = _safe_dict(player_state.get("reputation"))
    candidates = [merchant_id, "local", "global"]
    if merchant_id.startswith("merchant:"):
        candidates.append(merchant_id.split(":", 1)[1])
    for candidate in candidates:
        value = reputation.get(candidate)
        if isinstance(value, dict):
            return _safe_int(value.get("score", value.get("value", 0)), 0)
        if value is not None:
            return _safe_int(value, 0)
    return 0


def _charisma_value(player_state: Dict[str, Any]) -> int:
    stats = _safe_dict(player_state.get("stats"))
    attributes = _safe_dict(player_state.get("attributes"))
    return _safe_int(
        stats.get("charisma", attributes.get("charisma", player_state.get("charisma", 10))),
        10,
    )


def _scarcity_value(merchant_state: Dict[str, Any], item_id: str) -> int:
    stock = _safe_list(merchant_state.get("stock"))
    for row in stock:
        row = _safe_dict(row)
        if _safe_str(row.get("item_id")) != item_id:
            continue
        qty = max(0, _safe_int(row.get("qty"), 0))
        if qty <= 0:
            return 5
        if qty == 1:
            return 3
        if qty >= 8:
            return -1
        return 0
    return 0


def _causal_price_delta(merchant_state: Dict[str, Any]) -> tuple[int, int]:
    multiplier = _clamp(
        _safe_int(merchant_state.get("causal_price_multiplier_bps"), 10000),
        8000,
        15000,
    )
    return multiplier, multiplier - 10000


def _modifier_rows(
    *,
    player_state: Dict[str, Any],
    merchant_state: Dict[str, Any],
    merchant_id: str,
    item_id: str,
    kind: str,
) -> List[Dict[str, Any]]:
    charisma = _charisma_value(player_state)
    relationship = _relationship_value(player_state, merchant_id)
    reputation = _reputation_value(player_state, merchant_id)
    scarcity = _scarcity_value(merchant_state, item_id)
    causal_multiplier, causal_delta = _causal_price_delta(merchant_state)

    charisma_delta = _clamp(charisma - 10, -10, 15) * -100
    relationship_delta = _clamp(relationship, -100, 100) * -8
    reputation_delta = _clamp(reputation, -100, 100) * -5
    scarcity_delta = _clamp(scarcity, -5, 5) * 300

    rows = [
        {"modifier": "charisma", "value": charisma, "basis_points_delta": charisma_delta},
        {"modifier": "relationship", "value": relationship, "basis_points_delta": relationship_delta},
        {"modifier": "reputation", "value": reputation, "basis_points_delta": reputation_delta},
        {"modifier": "scarcity", "value": scarcity, "basis_points_delta": scarcity_delta},
        {
            "modifier": "causal_world_economy",
            "value": causal_multiplier,
            "basis_points_delta": causal_delta,
            "source": "deterministic_causal_runtime",
        },
    ]

    if kind == "sell":
        for row in rows:
            if row.get("modifier") != "causal_world_economy":
                row["basis_points_delta"] = -int(row["basis_points_delta"])

    return rows


def calculate_price_modifier(
    *,
    player_state: Dict[str, Any] | None = None,
    merchant_state: Dict[str, Any] | None = None,
    merchant_id: str = "merchant:elara",
    item_id: str = "",
    kind: str = "buy",
) -> Dict[str, Any]:
    player_state = _safe_dict(player_state)
    merchant_state = _safe_dict(merchant_state)
    kind = _safe_str(kind).strip().lower() or "buy"
    if kind not in {"buy", "sell"}:
        kind = "buy"

    rows = _modifier_rows(
        player_state=player_state,
        merchant_state=merchant_state,
        merchant_id=_safe_str(merchant_id) or "merchant:elara",
        item_id=_safe_str(item_id),
        kind=kind,
    )
    base_bps = DEFAULT_SELL_MULTIPLIER_BPS if kind == "sell" else 10000
    raw_bps = base_bps + sum(_safe_int(row.get("basis_points_delta"), 0) for row in rows)
    if kind == "sell":
        multiplier_bps = _clamp(raw_bps, MIN_SELL_MULTIPLIER_BPS, MAX_SELL_MULTIPLIER_BPS)
    else:
        multiplier_bps = _clamp(raw_bps, MIN_BUY_MULTIPLIER_BPS, MAX_BUY_MULTIPLIER_BPS)

    return {
        "kind": kind,
        "merchant_id": _safe_str(merchant_id) or "merchant:elara",
        "item_id": _safe_str(item_id),
        "base_multiplier_bps": base_bps,
        "raw_multiplier_bps": raw_bps,
        "multiplier_bps": multiplier_bps,
        "modifiers": rows,
        "source": SOURCE,
    }


def apply_price_modifier(
    base_price: Dict[str, Any],
    *,
    player_state: Dict[str, Any] | None = None,
    merchant_state: Dict[str, Any] | None = None,
    merchant_id: str = "merchant:elara",
    item_id: str = "",
    kind: str = "buy",
) -> Dict[str, Any]:
    normalized_base = normalize_currency(base_price)
    base_copper = max(0, currency_to_copper_value(normalized_base))
    modifier = calculate_price_modifier(
        player_state=player_state,
        merchant_state=merchant_state,
        merchant_id=merchant_id,
        item_id=item_id,
        kind=kind,
    )
    multiplier_bps = _safe_int(modifier.get("multiplier_bps"), 10000)
    adjusted_copper = int(round(base_copper * multiplier_bps / 10000))
    if base_copper > 0:
        adjusted_copper = max(MIN_PRICE_COPPER, adjusted_copper)
    adjusted_price = normalized_base if adjusted_copper == base_copper else copper_to_currency(adjusted_copper)

    return {
        "base_price": normalized_base,
        "base_price_copper": base_copper,
        "adjusted_price": adjusted_price,
        "adjusted_price_copper": adjusted_copper,
        "price_modifier": deepcopy(modifier),
        "source": SOURCE,
    }
