from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.currency import normalize_currency
from app.rpg.items.inventory_state import add_inventory_items, normalize_inventory_state

SOURCE = "deterministic_starter_loadout"

STARTER_CURRENCY: Dict[str, int] = {
    "gold": 0,
    "silver": 15,
    "copper": 0,
}

STARTER_ITEMS: List[Dict[str, Any]] = [
    {
        "item_id": "combat_knife",
        "qty": 1,
        "source": SOURCE,
    },
    {
        "item_id": "healing_potion",
        "qty": 1,
        "source": SOURCE,
    },
    {
        "item_id": "bandit_token",
        "qty": 1,
        "source": SOURCE,
    },
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def build_starter_loadout() -> Dict[str, Any]:
    return {
        "source": SOURCE,
        "currency": normalize_currency(STARTER_CURRENCY),
        "items": deepcopy(STARTER_ITEMS),
    }


def ensure_player_starter_loadout(
    simulation_state: Dict[str, Any],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Ensure a new player has canonical starter money and basic supplies.

    The helper is deterministic and idempotent by default. Existing sessions that
    already carry the starter marker are not mutated unless ``force`` is true.
    """
    state = _safe_dict(simulation_state)
    player_state = _safe_dict(state.get("player_state"))
    if not player_state:
        player_state = {}
        state["player_state"] = player_state

    existing_source = _safe_str(player_state.get("starter_loadout_source"))
    if existing_source == SOURCE and not force:
        return state

    loadout = build_starter_loadout()
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))

    if force or not _safe_list(inventory_state.get("items")):
        inventory_state = add_inventory_items(inventory_state, _safe_list(loadout.get("items")))

    current_currency = normalize_currency(inventory_state.get("currency"))
    if force or current_currency == normalize_currency({}):
        inventory_state["currency"] = normalize_currency(loadout.get("currency"))

    player_state["inventory_state"] = inventory_state
    player_state["starter_loadout_source"] = SOURCE
    state["player_state"] = player_state
    return state
