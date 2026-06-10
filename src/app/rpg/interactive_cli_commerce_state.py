"""Interactive CLI commerce state helpers.

This module models short-session commerce facts for interactive review runs without
claiming full shop persistence.  It records sell attempts as explicit commerce
state so presentation can report from state instead of only text cleanup.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

COMMERCE_STATE_VERSION = "interactive_cli_commerce_state_v1"
DEFAULT_MERCHANT_ID = "npc:bran"
DEFAULT_MERCHANT_NAME = "Bran"
SELLABLE_PROBE_ITEMS: tuple[str, ...] = ("ration", "rations", "provision", "provisions")
SELL_REQUEST_TERMS: tuple[str, ...] = (
    "sell",
    "sold",
    "trade",
    "barter",
    "value",
    "worth",
    "price",
    "how much",
    "copper would you give",
    "give me for",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _dedupe(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _safe_str(value).strip().lower()
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def default_commerce_state() -> Dict[str, Any]:
    """Return the starter commerce state for interactive feature probes."""

    return {
        "version": COMMERCE_STATE_VERSION,
        "merchant_id": DEFAULT_MERCHANT_ID,
        "merchant_name": DEFAULT_MERCHANT_NAME,
        "buyback_supported": False,
        "supported_operations": ["ask_price", "buy_room", "unsupported_sell_refusal"],
        "attempted_sells": [],
        "last_trade_action": {},
        "inventory_mutated": False,
        "currency_delta_copper": 0,
        "source": "starter_interactive_cli_commerce_state",
    }


def normalize_commerce_state(value: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Normalize arbitrary commerce state into a deterministic payload."""

    state = deepcopy(_safe_dict(value))
    attempted_sells = [deepcopy(_safe_dict(item)) for item in state.get("attempted_sells") or []]
    operations = _dedupe(state.get("supported_operations") or default_commerce_state()["supported_operations"])
    if not operations:
        operations = list(default_commerce_state()["supported_operations"])
    return {
        "version": COMMERCE_STATE_VERSION,
        "merchant_id": _safe_str(state.get("merchant_id") or DEFAULT_MERCHANT_ID),
        "merchant_name": _safe_str(state.get("merchant_name") or DEFAULT_MERCHANT_NAME),
        "buyback_supported": bool(state.get("buyback_supported", False)),
        "supported_operations": operations,
        "attempted_sells": attempted_sells,
        "last_trade_action": deepcopy(_safe_dict(state.get("last_trade_action"))),
        "inventory_mutated": bool(state.get("inventory_mutated", False)),
        "currency_delta_copper": int(state.get("currency_delta_copper") or 0),
        "source": _safe_str(state.get("source") or "interactive_cli_commerce_state"),
    }


def extract_commerce_state(turn: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Extract commerce state from a turn/result payload, falling back to defaults."""

    turn_dict = _safe_dict(turn)
    raw_result = _safe_dict(turn_dict.get("raw_result") or turn_dict.get("result"))
    for candidate in (
        turn_dict.get("interactive_cli_commerce_state"),
        raw_result.get("interactive_cli_commerce_state"),
        turn_dict.get("commerce_state"),
        raw_result.get("commerce_state"),
    ):
        if isinstance(candidate, dict):
            return normalize_commerce_state(candidate)
    return default_commerce_state()


def is_sell_request(player_input: str, requested_terms: Iterable[Any] = ()) -> bool:
    """Return true for ration/provision sell, value, or buyback requests."""

    combined = " ".join([_safe_str(player_input).lower(), " ".join(_safe_str(term).lower() for term in requested_terms)])
    if not any(item in combined for item in SELLABLE_PROBE_ITEMS):
        return False
    if any(term in combined for term in SELL_REQUEST_TERMS):
        return True
    return "ration" in combined and any(term in combined for term in ("copper", "coin", "give me", "how much"))


def item_from_sell_request(player_input: str) -> str:
    text = _safe_str(player_input).lower()
    if "provision" in text:
        return "provision"
    return "ration"


def apply_sell_attempt(state: Mapping[str, Any], *, player_input: str, turn_index: int = 0) -> Dict[str, Any]:
    """Record an unsupported sell attempt without mutating inventory or currency."""

    normalized = normalize_commerce_state(state)
    item = item_from_sell_request(player_input)
    attempt = {
        "turn_index": int(turn_index),
        "merchant_id": normalized["merchant_id"],
        "merchant_name": normalized["merchant_name"],
        "item": item,
        "quantity": 1,
        "requested_currency": "copper" if "copper" in _safe_str(player_input).lower() else "unspecified",
        "outcome": "unsupported_buyback_refusal",
        "reason": "merchant_buyback_not_supported",
        "inventory_mutated": False,
        "currency_delta_copper": 0,
    }
    normalized["attempted_sells"] = [*normalized["attempted_sells"], attempt]
    normalized["last_trade_action"] = attempt
    normalized["inventory_mutated"] = False
    normalized["currency_delta_copper"] = 0
    normalized["source"] = "interactive_cli_sell_attempt_state"
    return normalized


def describe_sell_attempt(state: Mapping[str, Any]) -> tuple[str, str]:
    """Return narration and NPC line for the current sell-attempt state."""

    normalized = normalize_commerce_state(state)
    action = _safe_dict(normalized.get("last_trade_action"))
    item = _safe_str(action.get("item") or "ration")
    merchant = normalized["merchant_name"]
    narration = f"{merchant} handles the request as a trade/sell attempt in the current commerce state."
    line = f"I can't buy that {item} from you yet; sell/buyback is not supported in the current trade state."
    return narration, line
