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
HANDOFF_SOURCE = "n1277_survival_relief_supply_handoff"
BALANCE_SOURCE = "n1278_survival_relief_balance_tuning"
NEEDS = ("hunger", "thirst", "fatigue")
# Thirst rises faster than hunger in the current deterministic tick (+2 vs +1),
# so N127.8 gives drink relief a larger but still bounded autoplay budget and a
# slightly earlier threshold.  These are coverage supplies, not hidden rewards:
# every item is explicit inventory consumed by the deterministic resolver.
MAX_GRANTS_PER_SESSION = {"food": 3, "drink": 4}
PRESSURE_THRESHOLDS = {"food": 55, "drink": 45}
PRESSURE_THRESHOLD = min(PRESSURE_THRESHOLDS.values())

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
    runtime["survival_autoplay_relief_balance_source"] = BALANCE_SOURCE
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
            "tags": ["food", "ration", "survival", SOURCE, BALANCE_SOURCE],
            "source": SOURCE,
            "balance_source": BALANCE_SOURCE,
        }
    else:
        item = {
            "item_id": f"autoplay_waterskin_{ordinal}",
            "name": "Autoplay Waterskin",
            "quantity": 1,
            "tags": ["drink", "water", "waterskin", "survival", SOURCE, BALANCE_SOURCE],
            "source": SOURCE,
            "balance_source": BALANCE_SOURCE,
        }
    items.append(item)
    inventory["items"] = items
    return item


def _is_autoplay_supply_item(item: Dict[str, Any]) -> bool:
    item = _safe_dict(item)
    if _safe_str(item.get("source")) in (SOURCE, HANDOFF_SOURCE):
        return True
    if _safe_str(item.get("balance_source")) == BALANCE_SOURCE:
        return True
    item_id = _item_identity(item)
    if item_id.startswith("autoplay_field_ration_") or item_id.startswith("autoplay_waterskin_"):
        return True
    tags = _item_tags(item)
    return SOURCE.lower() in tags or BALANCE_SOURCE.lower() in tags


def _item_key(item: Dict[str, Any]) -> str:
    key = _item_identity(item)
    return key or _safe_str(item.get("name")).lower()


def _copy_supply_items(source_session: Dict[str, Any], target_session: Dict[str, Any]) -> list[Dict[str, Any]]:
    source_sim = _simulation_state(source_session)
    target_sim = _simulation_state(target_session)
    if not source_sim or not target_sim:
        return []
    source_items = _safe_list(_inventory_state(source_sim).get("items"))
    target_inventory = _inventory_state(target_sim)
    target_items = list(_safe_list(target_inventory.get("items")))
    existing_keys = {_item_key(_safe_dict(item)) for item in target_items if _item_key(_safe_dict(item))}
    copied: list[Dict[str, Any]] = []
    for raw in source_items:
        item = copy.deepcopy(_safe_dict(raw))
        if not item or _item_quantity(item) <= 0 or not _is_autoplay_supply_item(item):
            continue
        key = _item_key(item)
        if key and key in existing_keys:
            continue
        item.setdefault("source", SOURCE)
        item["balance_source"] = _safe_str(item.get("balance_source") or BALANCE_SOURCE)
        tags = list(_safe_list(item.get("tags")))
        for tag in (HANDOFF_SOURCE, BALANCE_SOURCE):
            if tag not in tags:
                tags.append(tag)
        item["tags"] = tags
        target_items.append(item)
        if key:
            existing_keys.add(key)
        copied.append(item)
    target_inventory["items"] = target_items
    return copied


def _merge_counters_from_source(source_session: Dict[str, Any], target_session: Dict[str, Any], session_key: str | None) -> Dict[str, int]:
    source_runtime = _runtime_state(source_session)
    target_runtime = _runtime_state(target_session)
    source_counters = _safe_dict(source_runtime.get("survival_autoplay_relief_supply_grants"))
    target_counters = _safe_dict(target_runtime.get("survival_autoplay_relief_supply_grants"))
    key = _session_key(session_key)
    live = _IN_PROCESS_SUPPLY_GRANTS.setdefault(key, {}) if key else {}
    counters = {
        "food": max(_safe_int(source_counters.get("food"), 0), _safe_int(target_counters.get("food"), 0), _safe_int(live.get("food"), 0)),
        "drink": max(_safe_int(source_counters.get("drink"), 0), _safe_int(target_counters.get("drink"), 0), _safe_int(live.get("drink"), 0)),
    }
    target_runtime["survival_autoplay_relief_supply_grants"] = dict(counters)
    target_runtime["survival_autoplay_relief_supply_source"] = SOURCE
    target_runtime["survival_autoplay_relief_balance_source"] = BALANCE_SOURCE
    if key:
        _IN_PROCESS_SUPPLY_GRANTS[key] = dict(counters)
    return counters


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


def merge_survival_autoplay_relief_supplies_into_session(
    session: Dict[str, Any],
    source_session: Dict[str, Any],
    *,
    session_key: str | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Copy transient N127.6 supply items across a runtime reload boundary.

    The autoplay wrapper seeds supplies in the pre-turn selector session, but the
    authoritative runtime may reload the saved session before resolving the
    promoted command.  This handoff preserves only explicit N127.6 supply items
    and counters, keeping the deterministic resolver backed by real inventory.
    """

    session = copy.deepcopy(_safe_dict(session))
    source_session = _safe_dict(source_session)
    if not session or not source_session:
        return session, {"applied": False, "reason": "missing_session_or_source_session", "source": HANDOFF_SOURCE}
    simulation_state = _simulation_state(session)
    if not simulation_state:
        return session, {"applied": False, "reason": "missing_target_simulation_state", "source": HANDOFF_SOURCE}
    copied = _copy_supply_items(source_session, session)
    counters = _merge_counters_from_source(source_session, session, session_key)
    session = _mirror_session_roots(session, _simulation_state(session))
    summary = {
        "applied": bool(copied),
        "source": HANDOFF_SOURCE,
        "balance_source": BALANCE_SOURCE,
        "session_key": _session_key(session_key),
        "copied_count": len(copied),
        "copied_items": copied,
        "grant_counters": dict(counters),
        "limits": dict(MAX_GRANTS_PER_SESSION),
        "thresholds": dict(PRESSURE_THRESHOLDS),
    }
    runtime = _runtime_state(session)
    runtime["last_survival_autoplay_relief_supply_handoff_summary"] = copy.deepcopy(summary)
    session["runtime_state"] = runtime
    return session, summary


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

    if values.get("hunger", 0) >= PRESSURE_THRESHOLDS["food"] and not _has_item_kind(simulation_state, "food"):
        if counters.get("food", 0) < MAX_GRANTS_PER_SESSION["food"]:
            counters["food"] = counters.get("food", 0) + 1
            grants.append({"kind": "food", "need": "hunger", "need_value": values.get("hunger", 0), "threshold": PRESSURE_THRESHOLDS["food"], "item": _add_item(simulation_state, kind="food", ordinal=counters["food"])})

    if values.get("thirst", 0) >= PRESSURE_THRESHOLDS["drink"] and not _has_item_kind(simulation_state, "drink"):
        if counters.get("drink", 0) < MAX_GRANTS_PER_SESSION["drink"]:
            counters["drink"] = counters.get("drink", 0) + 1
            grants.append({"kind": "drink", "need": "thirst", "need_value": values.get("thirst", 0), "threshold": PRESSURE_THRESHOLDS["drink"], "item": _add_item(simulation_state, kind="drink", ordinal=counters["drink"])})

    _record_counter(session, session_key, counters)
    session = _mirror_session_roots(session, simulation_state)
    summary = {
        "applied": bool(grants),
        "source": SOURCE,
        "balance_source": BALANCE_SOURCE,
        "session_key": _session_key(session_key),
        "needs": values,
        "grant_count": len(grants),
        "grants": grants,
        "grant_counters": dict(counters),
        "limits": dict(MAX_GRANTS_PER_SESSION),
        "thresholds": dict(PRESSURE_THRESHOLDS),
    }
    runtime = _runtime_state(session)
    runtime["last_survival_autoplay_relief_supply_summary"] = copy.deepcopy(summary)
    session["runtime_state"] = runtime
    return session, summary
