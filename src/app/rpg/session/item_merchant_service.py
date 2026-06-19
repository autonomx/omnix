"""Player-facing item merchant service helpers.

This module composes deterministic merchant catalogs and session-level buy/sell
mutation into a compact service surface. Routes, UI, and autoplay can ask for a
menu, then apply a selected offer without letting presentation text own prices or
inventory changes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.rpg.session.inventory_items import display_item_name, inventory_quantity
from app.rpg.session.item_market import build_merchant_catalog, find_offer
from app.rpg.session.item_market_session import apply_session_market_action

MERCHANT_SERVICE_SOURCE = "engine_item_merchant_service_v1"
TRACE_LIMIT = 50


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _player(state: dict[str, Any]) -> dict[str, Any]:
    player = _safe_dict(state.get("player"))
    state["player"] = player
    return player


def _mechanics(state: dict[str, Any]) -> dict[str, Any]:
    mechanics = _safe_dict(state.get("mechanics"))
    state["mechanics"] = mechanics
    return mechanics


def _market_state(state: dict[str, Any]) -> dict[str, Any]:
    market = _safe_dict(state.get("item_market"))
    state["item_market"] = market
    catalogs = _safe_dict(market.get("catalogs"))
    market["catalogs"] = catalogs
    return market


def _session_genre(state: dict[str, Any], genre: str | None = None) -> str:
    if genre:
        return str(genre)
    metadata = _safe_dict(state.get("metadata"))
    identity = _safe_dict(state.get("character_identity"))
    return str(metadata.get("genre") or identity.get("genre") or metadata.get("campaign_template") or "classic_fantasy")


def _session_level(state: dict[str, Any], level: int | None = None) -> int:
    if level is not None:
        return max(1, int(level or 1))
    return max(1, int(_player(state).get("level") or 1))


def _session_reputation(state: dict[str, Any], reputation: int | None = None) -> int:
    if reputation is not None:
        return int(reputation or 0)
    player = _player(state)
    return int(player.get("merchant_reputation") or player.get("reputation") or 0)


def _prepend_trace(state: dict[str, Any], key: str, trace: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(trace)
    enriched["mechanics_source"] = MERCHANT_SERVICE_SOURCE
    enriched["turn"] = int(state.get("current_turn") or state.get("turn_count") or 0)
    enriched["timestamp"] = _utc_now()
    mechanics = _mechanics(state)
    mechanics[key] = [enriched, *_safe_list(mechanics.get(key))][:TRACE_LIMIT]
    mechanics["item_traces"] = [enriched, *_safe_list(mechanics.get("item_traces"))][:TRACE_LIMIT]
    return enriched


def _build_catalog(
    state: dict[str, Any],
    *,
    merchant_profile: str | None = None,
    genre: str | None = None,
    level: int | None = None,
    reputation: int | None = None,
) -> tuple[str, dict[str, Any]]:
    built = build_merchant_catalog(
        merchant_profile,
        genre=_session_genre(state, genre),
        level=_session_level(state, level),
        reputation=_session_reputation(state, reputation),
    )
    profile = _text(built.get("profile"), "general_store")
    catalog = {"profile": profile, "offers": _safe_list(built.get("offers")), "trace": _safe_dict(built.get("trace"))}
    catalogs = _safe_dict(_market_state(state).get("catalogs"))
    catalogs[profile] = deepcopy(catalog)
    _market_state(state)["catalogs"] = catalogs
    return profile, catalog


def _buy_offer_row(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "buy",
        "item_id": offer.get("item_id"),
        "name": offer.get("name"),
        "quantity_available": inventory_quantity(offer),
        "unit_price": _safe_dict(offer.get("buy_price")),
    }


def _sell_offer_row(item: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any] | None:
    item_id = _text(item.get("item_id") or item.get("id"))
    if not item_id:
        return None
    offer = find_offer(catalog, item_id)
    if not offer:
        return None
    return {
        "action": "sell",
        "item_id": item_id,
        "name": display_item_name(item),
        "quantity_owned": inventory_quantity(item),
        "unit_price": _safe_dict(offer.get("sell_price")),
    }


def build_item_merchant_menu(
    state: dict[str, Any],
    *,
    merchant_profile: str | None = None,
    genre: str | None = None,
    level: int | None = None,
    reputation: int | None = None,
    record_trace: bool = True,
) -> dict[str, Any]:
    """Build and cache a deterministic player-facing merchant menu."""

    mutable_state = state if isinstance(state, dict) else {}
    profile, catalog = _build_catalog(
        mutable_state,
        merchant_profile=merchant_profile,
        genre=genre,
        level=level,
        reputation=reputation,
    )
    player_inventory = _safe_list(_player(mutable_state).get("inventory"))
    buy_offers = [_buy_offer_row(_safe_dict(offer)) for offer in _safe_list(catalog.get("offers"))]
    sell_offers = [
        row for item in player_inventory if (row := _sell_offer_row(_safe_dict(item), catalog)) is not None
    ]
    trace = {
        "event": "item_merchant_menu_built",
        "merchant_profile": profile,
        "buy_offer_count": len(buy_offers),
        "sell_offer_count": len(sell_offers),
    }
    recorded = _prepend_trace(mutable_state, "item_merchant_service_traces", trace) if record_trace else None
    return {
        "ok": True,
        "merchant_profile": profile,
        "buy_offers": buy_offers,
        "sell_offers": sell_offers,
        "catalog": catalog,
        "recorded": bool(recorded),
        "mechanics_trace": recorded,
        "mechanics_source": MERCHANT_SERVICE_SOURCE,
    }


def apply_item_merchant_selection(
    state: dict[str, Any],
    item_id: str | None,
    *,
    action: str = "buy",
    quantity: int = 1,
    merchant_profile: str | None = None,
    genre: str | None = None,
    level: int | None = None,
    reputation: int | None = None,
    record_trace: bool = True,
) -> dict[str, Any]:
    """Apply a selected merchant menu action to mutable session state."""

    normalized_action = _norm(action)
    if normalized_action not in {"buy", "sell"}:
        return {"ok": False, "error": "unsupported_merchant_service_action", "action": action}
    mutable_state = state if isinstance(state, dict) else {}
    profile, _catalog = _build_catalog(
        mutable_state,
        merchant_profile=merchant_profile,
        genre=genre,
        level=level,
        reputation=reputation,
    )
    result = apply_session_market_action(
        mutable_state,
        item_id,
        action=normalized_action,
        quantity=max(1, int(quantity or 1)),
        merchant_profile=profile,
        genre=genre,
        level=level,
        reputation=reputation,
    )
    if not result.get("ok"):
        return {**result, "merchant_profile": profile, "mechanics_source": MERCHANT_SERVICE_SOURCE}
    trace = {
        "event": "item_merchant_selection_applied",
        "merchant_profile": profile,
        "action": normalized_action,
        "item_id": result.get("item", {}).get("item_id") or item_id,
        "quantity": max(1, int(quantity or 1)),
        "market_trace": result.get("mechanics_trace"),
    }
    recorded = _prepend_trace(mutable_state, "item_merchant_service_traces", trace) if record_trace else None
    return {
        **result,
        "merchant_profile": profile,
        "recorded": bool(recorded),
        "service_trace": recorded,
        "mechanics_source": MERCHANT_SERVICE_SOURCE,
    }
