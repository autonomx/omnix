"""The hero's gear in the one store (RQ-2.4): what document version 8 gathers there.

Before version 8 the hero's worn gear was kept a third time, in ``player_state.inventory`` (where combat read it),
and the older fight engine put its loot there too. The store (``inventory_state``) holds the pack and what is worn,
by slot; the play screen's sheet lists it. ``gather_gear`` moves what the third record held into the store (the
store's own entries win) and drops the record.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _key(item: dict[str, Any]) -> str:
    return str(item.get("item_id") or item.get("id") or item.get("name") or "")


def gather_gear(document: dict[str, Any]) -> dict[str, Any]:
    """``document`` with ``player_state.inventory`` folded into the store, or as it is when there is none."""
    simulation = document.get("simulation_state")
    player = simulation.get("player_state") if isinstance(simulation, dict) else None
    if not isinstance(player, dict) or "inventory" not in player:
        return document
    gathered = deepcopy(document)
    player = gathered["simulation_state"]["player_state"]
    old = player.pop("inventory")
    old = old if isinstance(old, dict) else {}
    store = player.get("inventory_state") if isinstance(player.get("inventory_state"), dict) else {}
    items = [dict(item) for item in store.get("items") or () if isinstance(item, dict)]
    held = {_key(item) for item in items}
    for item in old.get("items") or ():
        if isinstance(item, dict) and _key(item) and _key(item) not in held:
            items.append(dict(item))
            held.add(_key(item))
    equipment = {str(slot): str(item_id) for slot, item_id in (old.get("equipment") or {}).items()
                 if item_id and str(item_id) in held}
    equipment.update({str(slot): str(item_id) for slot, item_id in (store.get("equipment") or {}).items() if item_id})
    player["inventory_state"] = {**store, "items": items, "equipment": equipment}
    return gathered


__all__ = ["gather_gear"]
