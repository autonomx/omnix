from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str

MAX_WORLD_EVENTS = 64  # the campaign keeps the world's recent events, not all of them (F2)

# The world's event log, kept in the simulation it is handed: on a turn that is the causal tick's working copy
# (``session/causal_turn_runtime.causal_tick``), whose changes the tick hands the reducer as ``WorldTicked``.


def _ensure_world_event_state(working: Dict[str, Any]) -> Dict[str, Any]:
    log = working.get("world_event_state")
    if not isinstance(log, dict):
        log = {}
        working["world_event_state"] = log
    events = log.get("events")
    if not isinstance(events, list):
        events = []
        log["events"] = events
    return log


def add_world_event(
    working: Dict[str, Any],
    event: Dict[str, Any],
) -> Dict[str, Any]:
    event = deepcopy(_safe_dict(event))
    event_id = _safe_str(event.get("event_id"))
    if not event_id:
        return {}

    log = _ensure_world_event_state(working)
    events = _safe_list(log.get("events"))
    for existing in events:
        existing = _safe_dict(existing)
        if _safe_str(existing.get("event_id")) == event_id:
            return deepcopy(existing)

    events.append(event)
    if len(events) > MAX_WORLD_EVENTS:
        del events[:-MAX_WORLD_EVENTS]
    return deepcopy(event)


def get_world_event_state(working: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(_ensure_world_event_state(working))
