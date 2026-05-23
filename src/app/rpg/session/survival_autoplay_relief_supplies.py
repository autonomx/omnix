from __future__ import annotations

"""Bounded deterministic survival supplies for autoplay coverage.

N127.6 makes hunger/thirst relief observable in long autoplay runs without using
an LLM or inventing hidden outcomes.  When pressure is high and the current
session has no backed food/drink option, the autoplay harness may seed a small,
explicit survival kit.  The seeded items are normal inventory entries consumed
by the existing deterministic N123.2 resolver.
"""

import copy
from typing import Any, Dict, Tuple

SOURCE = "n1276_survival_hunger_thirst_relief_coverage"
NEEDS = ("hunger", "thirst", "fatigue")
MAX_GRANTS_PER_SESSION = {"food": 2, "drink": 2}
PRESSURE_THRESHOLD = 50

_IN_PROCESS_SUPPLY_GRANTS: Dict[str, Dict[str, int]] = {}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _clamp_need(value: Any) -> int:
    return max(0, min(100, _safe_int(value, 0)))


def reset_survival_autoplay_supply_grants(session_key: str | None = None) -> None:
    key = _safe_str(session_key).strip()
    if key:
        _IN_PROCESS_SUPPLY_GRANTS.pop(key, None)
    else:
        _IN_PROCESS_SUPPLY_GRANTS.clear()


def _session_key(value: Any) -> str:
    return _safe_str(value).strip()


def _simulation_state(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    if simulation_state:
        return simulation_state
    state = _safe_dict(session.get("state"))
    return _safe_dict(state.get("simulation_state")) or state


def _runtime_state(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    session["runtime_state"] = runtime
    return runtime


def _player_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    player = _safe_dict(simulation_state.get("player_state"))
    simulation_state["player_state"] = player
    return player


def _inventory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player = _player_state(simulation_state)
    inventory = _safe_dict(player.get("inventory_state"))
    inventory.setdefault("items", [])
    inventory.setdefault("currency", _safe_dict(inventory.get("currency")))
    player["inventory_state"] = inventory
    return inventory


def _needs(simulation_state: Dict[str, Any]) -> Dict[str, int]:
    simulation_state = _safe_dict(simulation_state)
    climate = _safe_dict(simulation_state.get("climate_survival"))
    survival = _safe_dict(climate.get("survival"))
    player = _safe_dict(simulation_state.get("player_state"))
    resources = _safe_dict(player.get("resources"))
    needs = _safe_dict(simulation_state.get("needs"))
    return {
        need: _clamp_need(survival.get(need, resources.get(need, needs.get(need, 0))))
        for need in NEEDS
    }


def _item_quantity(item: Dict[str, Any]) -> int:
    return max(0, _safe_int(item.get("quantity", item.get("qty", 1)), 1))


def _item_identity(item: Dict[str, Any]) -> str:
    return _safe_str(item.get("item_id") or item.get("id") or item.get("key") or item.get("name")).lower()


def _item_tags(item: Dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("tags", "item_tags", "categories"):
        tags.extend(_safe_str(value).lower() for value in _safe_list(item.get(key)))
    kind = _safe_str(item.get("kind") or item.get("type") or item.get("category")).lower()
    if kind:
        tags.append(kind)
    return tags


def _has_item_kind(simulation_state: Dict[str, Any], kind: str) -> bool:
    inventory = _inventory_state(simulation_state)
    for raw in _safe_list(inventory.get("items")):
        item = _safe_dict(raw)
        if _item_quantity(item) <= 0:
            continue
        haystack = " ".join([_item_identity(item), _safe_str(item.get("name")).lower()] + _item_tags(item))
        if kind == "food" and any(term in haystack for term in ("food", "ration", "meal", "bread", "stew", "fruit", "meat")):
            return True
        if kind == "drink" and any(term in haystack for term in ("drink", "water", "waterskin", "canteen", "ale", "wine", "beer")):
            return True
    return False


def _grant_counters(session: Dict[str, Any], session_key: str | None) -> Dict[str, int]:
    runtime = _runtime_state(session)
    persisted = _safe_dict(runtime.get("survival_autoplay_relief_supply_grants"))
    key = _session_key(session_key)
    live = _IN_PROCESS_SUPPLY_GRANTS.setdefault(key, {}) if key else {}
    counters = {
        "food": max(_safe_int(persisted.get("food"), 0), _safe_int(live.get("food"), 0)),
        "drink": max(_safe_int(persisted.get("drink"), 0), _safe_int(live.get("drink"), 0)),
    }
    if key:
        _IN_PROCESS_SUPPLY_GRANTS[key] = dict(counters)
    runtime["survival_autoplay_relief_supply_grants"] = dict(counters)
    return counters


def _record_counter(session: Dict[str, Any], session_key: str | None, counters: Dict[str, int]) -> None:
    runtime = _runtime_state(session)
    runtime["survival_autoplay_relief_supply_grants"] = dict(counters)
    runtime["survival_autoplay_relief_supply_source"] = SOURCE
    key = _session_key(session_key)
    if key:
        _IN_PROCESS_SUPPLY_GRANTS[key] = dict(counters)


def _add_item(simulation_state: Dict[str, Any], *, kind: str, ordinal: int) -> Dict[str, Any]:
    inventory = _inventory_state(simulation_state)
    items = list(_safe_list(inventory.get("items")))
    if kind == "food":
        item = {
            "item_id": f"autoplay_field_ration_{ordinal}",
            "name": "Autoplay Field Ration",
            "quantity": 1,
            "tags": ["food", "ration", "survival", SOURCE],
            "source": SOURCE,
        }
    else:
        item = {
            "item_id": f"autoplay_waterskin_{ordinal}",
            "name": "Autoplay Waterskin",
            "quantity": 1,
            "tags": ["drink", "water", "waterskin", "survival", SOURCE],
            "source": SOURCE,
        }
    items.append(item)
    inventory["items"] = items
    return item


def _mirror_session_roots(session: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    session["simulation_state"] = simulation_state
    state = _safe_dict(session.get("state"))
    state["simulation_state"] = copy.deepcopy(simulation_state)
    state["player_state"] = copy.deepcopy(_safe_dict(simulation_state.get("player_state")))
    session["state"] = state
    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = copy.deepcopy(simulation_state)
    metadata["player_state"] = copy.deepcopy(_safe_dict(simulation_state.get("player_state")))
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload
    return session


def ensure_survival_autoplay_relief_supplies(
    session: Dict[str, Any],
    *,
    session_key: str | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Seed bounded food/drink inventory only when high pressure lacks relief.

    Returns ``(session, summary)``.  The summary is explicit evidence that the
    long-run autoplay harness added deterministic supplies for coverage.
    """

    session = copy.deepcopy(_safe_dict(session))
    simulation_state = _simulation_state(session)
    if not session or not simulation_state:
        return session, {"applied": False, "reason": "missing_session_or_simulation_state", "source": SOURCE}

    values = _needs(simulation_state)
    counters = _grant_counters(session, session_key)
    grants: list[Dict[str, Any]] = []

    if values.get("hunger", 0) >= PRESSURE_THRESHOLD and not _has_item_kind(simulation_state, "food"):
        if counters.get("food", 0) < MAX_GRANTS_PER_SESSION["food"]:
            counters["food"] = counters.get("food", 0) + 1
            grants.append({"kind": "food", "need": "hunger", "need_value": values.get("hunger", 0), "item": _add_item(simulation_state, kind="food", ordinal=counters["food"])})

    if values.get("thirst", 0) >= PRESSURE_THRESHOLD and not _has_item_kind(simulation_state, "drink"):
        if counters.get("drink", 0) < MAX_GRANTS_PER_SESSION["drink"]:
            counters["drink"] = counters.get("drink", 0) + 1
            grants.append({"kind": "drink", "need": "thirst", "need_value": values.get("thirst", 0), "item": _add_item(simulation_state, kind="drink", ordinal=counters["drink"])})

    _record_counter(session, session_key, counters)
    session = _mirror_session_roots(session, simulation_state)
    summary = {
        "applied": bool(grants),
        "source": SOURCE,
        "session_key": _session_key(session_key),
        "needs": values,
        "grant_count": len(grants),
        "grants": grants,
        "grant_counters": dict(counters),
        "limits": dict(MAX_GRANTS_PER_SESSION),
    }
    runtime = _runtime_state(session)
    runtime["last_survival_autoplay_relief_supply_summary"] = copy.deepcopy(summary)
    session["runtime_state"] = runtime
    return session, summary
