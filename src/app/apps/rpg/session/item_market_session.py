"""Session-level item market action helpers.

This module bridges deterministic merchant catalogs and transaction mutation into a
session-state helper without depending on route or UI request schemas. Loadout,
routes, autoplay, and tests can use it to apply buy/sell actions consistently.
"""
from __future__ import annotations


from typing import Any

from app.apps.rpg.session.inventory_items import inventory_quantity
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _market_state(state: dict[str, Any]) -> dict[str, Any]:
    market = _safe_dict(state.get("item_market"))
    state["item_market"] = market
    catalogs = _safe_dict(market.get("catalogs"))
    market["catalogs"] = catalogs
    return market


def market_offer_quantities(state: dict[str, Any], merchant_profile: str = "general_store") -> dict[str, int]:
    """Return current cached offer quantities for diagnostics/tests."""

    catalogs = _safe_dict(_market_state(state).get("catalogs"))
    catalog = _safe_dict(catalogs.get(merchant_profile))
    return {
        _text(offer.get("item_id") or offer.get("name")): inventory_quantity(_safe_dict(offer))
        for offer in _safe_list(catalog.get("offers"))
    }
