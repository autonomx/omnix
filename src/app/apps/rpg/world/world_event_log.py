from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str

MAX_WORLD_EVENTS = 160


def _ensure_world_event_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = simulation_state.get("world_event_state")
    if not isinstance(state, dict):
        state = {}
        simulation_state["world_event_state"] = state
    events = state.get("events")
    if not isinstance(events, list):
        events = []
        state["events"] = events
    return state


def add_world_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
) -> Dict[str, Any]:
    event = deepcopy(_safe_dict(event))
    event_id = _safe_str(event.get("event_id"))
    if not event_id:
        return {}

    state = _ensure_world_event_state(simulation_state)
    events = _safe_list(state.get("events"))
    for existing in events:
        existing = _safe_dict(existing)
        if _safe_str(existing.get("event_id")) == event_id:
            return deepcopy(existing)

    events.append(event)
    if len(events) > MAX_WORLD_EVENTS:
        del events[:-MAX_WORLD_EVENTS]
    return deepcopy(event)


def get_world_event_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(_ensure_world_event_state(simulation_state))
