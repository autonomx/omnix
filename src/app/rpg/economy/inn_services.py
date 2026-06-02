from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.economy.currency import (
    can_afford,
    get_player_currency,
    normalize_currency,
    set_player_currency,
    subtract_currency_cost,
)

SOURCE = "deterministic_inn_services"
DEFAULT_INN_ID = "inn:rusty_flagon"
DEFAULT_KEEPER_ID = "npc:bran"
ROOM_PRICE = {"gold": 0, "silver": 5, "copper": 0}
REST_DURATION_TICKS = 8


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def build_room_service_offer(*, inn_id: str = DEFAULT_INN_ID, keeper_id: str = DEFAULT_KEEPER_ID) -> Dict[str, Any]:
    return {
        "service_id": "service:inn_room_rest",
        "inn_id": _safe_str(inn_id or DEFAULT_INN_ID),
        "keeper_id": _safe_str(keeper_id or DEFAULT_KEEPER_ID),
        "name": "Common room and rest",
        "price": normalize_currency(ROOM_PRICE),
        "duration_ticks": REST_DURATION_TICKS,
        "effects": {
            "hp": "restore_to_max",
            "fatigue": "clear",
            "rested": True,
        },
        "source": SOURCE,
    }


def _apply_rest_effects(state: Dict[str, Any], *, tick: int, duration_ticks: int) -> Dict[str, Any]:
    player_state = _safe_dict(state.get("player_state"))
    if not player_state:
        player_state = {}
        state["player_state"] = player_state

    max_hp = _safe_int(player_state.get("max_hp"), 0)
    if max_hp <= 0:
        max_hp = _safe_int(player_state.get("hp"), 10) or 10
        player_state["max_hp"] = max_hp
    player_state["hp"] = max_hp
    player_state["fatigue"] = 0

    rest_state = _safe_dict(player_state.get("rest_state"))
    rooms_rented = _safe_int(rest_state.get("rooms_rented"), 0) + 1
    rest_state.update(
        {
            "rested": True,
            "last_rest_tick": int(tick or 0),
            "rested_until_tick": int(tick or 0) + max(1, _safe_int(duration_ticks, REST_DURATION_TICKS)),
            "rooms_rented": rooms_rented,
            "source": SOURCE,
        }
    )
    player_state["rest_state"] = rest_state
    state["player_state"] = player_state
    return state


def rent_room_and_rest(
    simulation_state: Dict[str, Any],
    *,
    inn_id: str = DEFAULT_INN_ID,
    keeper_id: str = DEFAULT_KEEPER_ID,
    tick: int = 0,
) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)
    offer = build_room_service_offer(inn_id=inn_id, keeper_id=keeper_id)
    price = normalize_currency(offer.get("price"))
    before_currency = get_player_currency(state)
    if not can_afford(before_currency, price):
        return _service_response(
            False,
            "insufficient_funds",
            state,
            offer,
            before_currency=before_currency,
            after_currency=before_currency,
            tick=tick,
        )

    after_currency = subtract_currency_cost(before_currency, price)
    set_player_currency(state, after_currency)
    _apply_rest_effects(state, tick=tick, duration_ticks=_safe_int(offer.get("duration_ticks"), REST_DURATION_TICKS))

    economy_state = _safe_dict(state.get("economy_state"))
    service_log = list(economy_state.get("service_transaction_log") or [])
    log_entry = _service_log_entry(offer, tick=tick, reason="room_rest_completed")
    service_log.append(log_entry)
    economy_state["service_transaction_log"] = service_log[-50:]
    state["economy_state"] = economy_state

    return _service_response(
        True,
        "room_rest_completed",
        state,
        offer,
        before_currency=before_currency,
        after_currency=after_currency,
        transaction_log_entry=log_entry,
        tick=tick,
    )


def _service_log_entry(offer: Dict[str, Any], *, tick: int, reason: str) -> Dict[str, Any]:
    return {
        "kind": "service",
        "service_id": _safe_str(offer.get("service_id")),
        "item_id": _safe_str(offer.get("service_id")),
        "qty": 1,
        "price": normalize_currency(offer.get("price")),
        "tick": int(tick or 0),
        "reason": reason,
        "source": SOURCE,
    }


def _service_response(
    resolved: bool,
    reason: str,
    simulation_state: Dict[str, Any],
    offer: Dict[str, Any],
    *,
    before_currency: Any,
    after_currency: Any,
    transaction_log_entry: Dict[str, Any] | None = None,
    tick: int = 0,
) -> Dict[str, Any]:
    return {
        "resolved": resolved,
        "changed_state": bool(resolved),
        "action_type": "rent_room_rest",
        "reason": reason,
        "service_id": _safe_str(offer.get("service_id")),
        "inn_id": _safe_str(offer.get("inn_id")),
        "keeper_id": _safe_str(offer.get("keeper_id")),
        "price": normalize_currency(offer.get("price")),
        "before_currency": normalize_currency(before_currency),
        "after_currency": normalize_currency(after_currency),
        "transaction_log_entry": deepcopy(_safe_dict(transaction_log_entry)),
        "service_offer": deepcopy(offer),
        "simulation_state": simulation_state,
        "tick": int(tick or 0),
        "source": SOURCE,
    }
