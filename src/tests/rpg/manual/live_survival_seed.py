from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _reset_manual_session_artifacts,
    _sync_manual_simulation_state,
)

DEFAULT_NEEDS = {"hunger": 80, "thirst": 82, "fatigue": 78}
DEFAULT_ITEMS: List[Dict[str, Any]] = [
    {"item_id": "trail_ration", "name": "Trail Ration", "quantity": 1, "tags": ["food", "ration"]},
    {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
]
DEFAULT_CURRENCY = {"gold": 1, "silver": 10, "copper": 20}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _clamp(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        number = 0
    return max(0, min(100, number))


def _need_warnings(needs: Dict[str, Any]) -> List[str]:
    return [f"{key}_high" for key in ("hunger", "thirst", "fatigue") if _clamp(needs.get(key)) >= 70]


def build_live_seed_payload(
    *,
    needs: Dict[str, Any] | None = None,
    items: List[Dict[str, Any]] | None = None,
    currency: Dict[str, Any] | None = None,
    location_id: str = "loc_tavern",
) -> Dict[str, Any]:
    raw_needs = _safe_dict(needs or DEFAULT_NEEDS)
    normalized_needs = {
        "hunger": _clamp(raw_needs.get("hunger", DEFAULT_NEEDS["hunger"])),
        "thirst": _clamp(raw_needs.get("thirst", DEFAULT_NEEDS["thirst"])),
        "fatigue": _clamp(raw_needs.get("fatigue", DEFAULT_NEEDS["fatigue"])),
    }
    raw_currency = _safe_dict(currency or DEFAULT_CURRENCY)
    climate = {
        "format_version": "n1231_climate_survival_state_v1",
        "runtime_enforced": True,
        "source": "n1262_live_runtime_survival_seed",
        "tick": 0,
        "minutes_per_turn": 15,
        "survival": {**normalized_needs, "warnings": _need_warnings(normalized_needs)},
    }
    return {
        "location_id": _safe_str(location_id) or "loc_tavern",
        "needs": normalized_needs,
        "items": [deepcopy(_safe_dict(item)) for item in (items if items is not None else DEFAULT_ITEMS) if _safe_dict(item)],
        "currency": {
            "gold": _clamp(raw_currency.get("gold", DEFAULT_CURRENCY["gold"])),
            "silver": _clamp(raw_currency.get("silver", DEFAULT_CURRENCY["silver"])),
            "copper": _clamp(raw_currency.get("copper", DEFAULT_CURRENCY["copper"])),
        },
        "climate_survival": climate,
    }


def _apply_to_simulation(simulation_state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    location_id = _safe_str(payload.get("location_id")) or "loc_tavern"
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    simulation_state["player_state"] = player_state
    player_state["inventory_state"] = inventory_state
    simulation_state["location_id"] = location_id
    simulation_state["current_location_id"] = location_id
    player_state["location_id"] = location_id
    player_state["current_location_id"] = location_id
    player_state["resources"] = dict(_safe_dict(payload.get("needs")))
    inventory_state["items"] = [deepcopy(_safe_dict(item)) for item in _safe_list(payload.get("items")) if _safe_dict(item)]
    inventory_state["currency"] = dict(_safe_dict(payload.get("currency")))
    inventory_state.setdefault("capacity", 50)
    inventory_state.setdefault("equipment", {})
    inventory_state.setdefault("last_loot", [])
    simulation_state["climate_survival"] = deepcopy(_safe_dict(payload.get("climate_survival")))
    return simulation_state


def _apply_to_session(session: Dict[str, Any], session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    manifest = _safe_dict(session.get("manifest"))
    manifest["id"] = session_id
    manifest["session_id"] = session_id
    manifest.setdefault("schema_version", 2)
    manifest.setdefault("title", "N126.2 Live Survival Seed Smoke")
    manifest.setdefault("status", "active")
    session["manifest"] = manifest
    session["id"] = session_id
    session["session_id"] = session_id
    simulation_state = _apply_to_simulation(_safe_dict(session.get("simulation_state")), payload)
    session["simulation_state"] = simulation_state
    state = _safe_dict(session.get("state"))
    state["simulation_state"] = deepcopy(simulation_state)
    state["player_state"] = deepcopy(_safe_dict(simulation_state.get("player_state")))
    state["climate_survival"] = deepcopy(_safe_dict(simulation_state.get("climate_survival")))
    session["state"] = state
    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = deepcopy(simulation_state)
    metadata["player_state"] = deepcopy(_safe_dict(simulation_state.get("player_state")))
    metadata["climate_survival"] = deepcopy(_safe_dict(simulation_state.get("climate_survival")))
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["tick"] = 0
    runtime_state["last_turn_contract"] = {}
    runtime_state["last_turn_result"] = {}
    runtime_state["n1262_live_survival_seed"] = {"source": "n1262_live_runtime_survival_seed", "needs": dict(_safe_dict(payload.get("needs")))}
    session["runtime_state"] = runtime_state
    _sync_manual_simulation_state(session)
    return session


def seed_live_survival_session(
    session_id: str,
    *,
    needs: Dict[str, Any] | None = None,
    items: List[Dict[str, Any]] | None = None,
    currency: Dict[str, Any] | None = None,
    location_id: str = "loc_tavern",
    reset_first: bool = True,
) -> Dict[str, Any]:
    session_id = _safe_str(session_id).strip()
    if not session_id:
        raise ValueError("session_id_required")
    if reset_first:
        _reset_manual_session_artifacts(session_id)
    session = _ensure_manual_session(session_id)
    payload = build_live_seed_payload(needs=needs, items=items, currency=currency, location_id=location_id)
    session = _apply_to_session(session, session_id, payload)
    from app.rpg.session.service import save_session

    saved = save_session(session)
    return {"ok": True, "session_id": session_id, "seed_payload": payload, "saved_manifest": deepcopy(_safe_dict(saved.get("manifest")))}
