"""Deterministic RPG survival state model.

Bundle BA keeps survival in the real runtime package instead of autoplay
fragment overlays.  The functions here are pure, bounded, and JSON-safe so
session runtime code can persist them directly in ``simulation_state``.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping
from app.apps.rpg.foundation.safe_values import mapping_copy as _safe_dict

SURVIVAL_STATE_KEY = "survival"
SURVIVAL_EVENT_LIMIT = 32
SURVIVAL_MIN = 0
SURVIVAL_MAX = 100

DEFAULT_SURVIVAL_STATE: Dict[str, Any] = {
    "enabled": True,
    "hunger": 0,
    "thirst": 0,
    "fatigue": 0,
    "last_food_turn": None,
    "last_water_turn": None,
    "last_rest_turn": None,
    "events": [],
}

DEFAULT_SURVIVAL_TICK_RATES: Dict[str, int] = {
    "hunger": 1,
    "thirst": 2,
    "fatigue": 1,
}


_NEED_KEYS = ("hunger", "thirst", "fatigue")


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _clamp_need(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 0
    return max(SURVIVAL_MIN, min(SURVIVAL_MAX, numeric))


def _bounded_events(events: Iterable[Any]) -> List[Dict[str, Any]]:
    bounded: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        cleaned = dict(event)
        cleaned.setdefault("source", "runtime_survival_state")
        bounded.append(cleaned)
    return bounded[-SURVIVAL_EVENT_LIMIT:]


def normalize_survival_state(value: Any, *, enabled_default: bool = True) -> Dict[str, Any]:
    """Return a bounded, JSON-serializable survival state.

    Unknown keys are intentionally dropped so the persisted state cannot grow
    without bounds or smuggle LLM-generated effects into the runtime contract.
    """
    raw = _safe_dict(value)
    state = deepcopy(DEFAULT_SURVIVAL_STATE)
    state["enabled"] = _safe_bool(raw.get("enabled"), enabled_default)
    for key in _NEED_KEYS:
        state[key] = _clamp_need(raw.get(key, state[key]))
    for key in ("last_food_turn", "last_water_turn", "last_rest_turn"):
        turn_value = raw.get(key)
        if turn_value is None or turn_value == "":
            state[key] = None
        else:
            try:
                state[key] = int(turn_value)
            except (TypeError, ValueError):
                state[key] = None
    state["events"] = _bounded_events(raw.get("events", []))
    return state
