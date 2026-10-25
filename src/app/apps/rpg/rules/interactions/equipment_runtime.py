from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.apps.rpg.rules.interactions.item_catalog import get_item_definition, infer_definition_id_from_name
from app.apps.rpg.rules.interactions.item_model import normalize_item_instance
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str

DEFAULT_STATS = {
    "damage_min": 0,
    "damage_max": 1,
    "armor": 0,
    "accuracy_bonus": 0,
    "range": 1,
    "stealth_bonus": 0,
    "stealth_penalty": 0,
    "encumbrance_penalty": 0,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _store(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """The hero's one store: the pack and what is worn (RQ-2.4)."""
    return _safe_dict(_safe_dict(simulation_state.get("player_state")).get("inventory_state"))


def _inventory_for_actor(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    if actor_id in {"", "player"}:
        # The hero's pack and gear are the one store (inventory_state); reading them writes nothing.
        store = _store(simulation_state)
        return {"items": list(_safe_list(store.get("items"))), "equipment": dict(_safe_dict(store.get("equipment")))}

    party_state = _safe_dict(_safe_dict(simulation_state.get("player_state")).get("party_state"))
    for companion in _safe_list(party_state.get("companions")):
        companion = _safe_dict(companion)
        if _safe_str(companion.get("npc_id")) == actor_id:
            inv = _safe_dict(companion.get("inventory"))
            if not isinstance(inv.get("items"), list):
                inv["items"] = []
            if not isinstance(inv.get("equipment"), dict):
                inv["equipment"] = {}
            companion["inventory"] = inv
            return inv

    return {}


def _find_item(items, item_id: str) -> Dict[str, Any]:
    for item in _safe_list(items):
        item = normalize_item_instance(_safe_dict(item))
        if _safe_str(item.get("item_id")) == item_id:
            return item
    return {}


def _item_equipment(item: Dict[str, Any]) -> Dict[str, Any]:
    """An item's equipment block; a world's own weapon fights as the kind its name ends in ("Iron Dagger": a dagger)."""
    equipment = _safe_dict(item.get("equipment"))
    if _safe_dict(equipment.get("stats")):
        return equipment
    for word in reversed(_safe_str(item.get("name")).casefold().split()):
        kind = _safe_dict(get_item_definition(infer_definition_id_from_name(word)).get("equipment"))
        if _safe_dict(kind.get("stats")):
            return kind
    return equipment


def project_equipment_stats(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str = "player",
) -> Dict[str, Any]:
    inv = _inventory_for_actor(simulation_state, actor_id)
    carried = _safe_list(inv.get("items"))
    if not carried and actor_id in {"", "player"}:
        # The hero's pack is the inventory_state; what is no longer carried no longer counts.
        carried = _safe_list(_store(simulation_state).get("items"))
    items = [normalize_item_instance(_safe_dict(item)) for item in carried]
    equipment = _safe_dict(inv.get("equipment"))

    stats = deepcopy(DEFAULT_STATS)
    equipped_items = []

    for slot, item_id in equipment.items():
        item = _find_item(items, _safe_str(item_id))
        if not item:
            continue

        item_equipment = _item_equipment(item)
        item_stats = _safe_dict(item_equipment.get("stats"))
        for key, value in item_stats.items():
            stats[key] = _safe_int(stats.get(key), 0) + _safe_int(value, 0)

        equipped_items.append({
            "slot": _safe_str(slot),
            "item_id": _safe_str(item_id),
            "definition_id": _safe_str(item.get("definition_id")),
            "name": _safe_str(item.get("name")),
            "stats": deepcopy(item_stats),
        })

    encumbrance = _safe_str(inv.get("encumbrance_state"))
    penalty = 0
    if encumbrance == "burdened":
        penalty = 1
    elif encumbrance == "overloaded":
        penalty = 3
    elif encumbrance == "immobile":
        penalty = 99

    stats["encumbrance_penalty"] = penalty

    result = {
        "projected": True,
        "actor_id": actor_id,
        "stats": stats,
        "equipped_items": equipped_items,
        "source": "deterministic_equipment_runtime",
    }

    inv["equipment_stats"] = result
    return result
