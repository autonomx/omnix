"""Route-free dispatcher for deterministic RPG item session actions.

The lower-level bridges remain the source of truth for each item subsystem. This
module gives autoplay, tests, and future routes one compact entry point without
adding a route schema or presentation dependency.
"""
from __future__ import annotations

from typing import Any

from app.apps.rpg.session.item_effect_session import available_item_effects_for_session
from app.apps.rpg.session.item_market_session import market_offer_quantities
from app.apps.rpg.session.item_pickup_session import available_scene_pickups_for_session
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict

ITEM_SESSION_ACTIONS_SOURCE = "engine_item_session_actions_v1"


def available_item_session_actions(state: dict[str, Any], *, merchant_profile: str = "general_store") -> dict[str, Any]:
    """Return a deterministic snapshot of available session-level item actions."""

    state = _safe_dict(state)
    pickups = available_scene_pickups_for_session(state)
    effects = available_item_effects_for_session(state)
    market_quantities = market_offer_quantities(state, merchant_profile)
    actions = {
        "pickup": bool(pickups),
        "effect": bool(effects),
        "market": bool(market_quantities),
        "recipe_discovery": True,
        "report": True,
        "combat": bool(state.get("player") and _safe_dict(state.get("combat") or {}).get("participants")),
    }
    return {
        "actions": actions,
        "pickups": pickups,
        "effects": effects,
        "market_offer_quantities": market_quantities,
        "mechanics_source": ITEM_SESSION_ACTIONS_SOURCE,
    }
