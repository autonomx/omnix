"""Bundle BE — canonical survival save/load normalization.

The BA runtime state lives at ``simulation_state['survival']``.  This module is
used by session save/load/export/import boundaries so malformed, legacy, or
LLM-expanded survival payloads cannot become persistent truth.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, Tuple

from app.rpg.survival import SURVIVAL_STATE_KEY, normalize_survival_state

SURVIVAL_PERSISTENCE_SOURCE = "runtime_survival_persistence"

_NEED_KEYS: Tuple[str, str, str] = ("hunger", "thirst", "fatigue")
_LAST_TURN_KEYS: Tuple[str, str, str] = (
    "last_food_turn",
    "last_water_turn",
    "last_rest_turn",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _has_any_need(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in _NEED_KEYS)


def _legacy_survival_candidate(simulation_state: Mapping[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    climate = _safe_dict(simulation_state.get("climate_survival"))
    player_climate = _safe_dict(player_state.get("climate_survival"))

    candidates = (
        _safe_dict(climate.get("survival")),
        _safe_dict(simulation_state.get("needs")),
        _safe_dict(player_state.get("needs")),
        _safe_dict(player_climate.get("survival")),
    )
    for candidate in candidates:
        if _has_any_need(candidate):
            return candidate
    return {}


def _canonical_survival_seed(simulation_state: Mapping[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    root_survival = _safe_dict(simulation_state.get(SURVIVAL_STATE_KEY))
    if root_survival:
        return root_survival
    return _legacy_survival_candidate(simulation_state)


def normalize_survival_for_persistence(simulation_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Return simulation_state with bounded canonical survival state.

    Unknown survival keys are pruned by ``normalize_survival_state``.  Legacy
    climate/needs fields are left untouched for backward compatibility, but they
    no longer act as authoritative state after canonical survival is present.
    """
    simulation_state = deepcopy(_safe_dict(simulation_state))
    state = normalize_survival_state(_canonical_survival_seed(simulation_state))
    simulation_state[SURVIVAL_STATE_KEY] = state
    return simulation_state


def normalize_session_survival_for_persistence(session: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a whole session at save/load/export/import boundaries."""
    session = deepcopy(_safe_dict(session))
    simulation_state = normalize_survival_for_persistence(
        _safe_dict(session.get("simulation_state"))
    )
    session["simulation_state"] = simulation_state
    return session


def survival_persistence_summary(simulation_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Small bounded diagnostic summary for tests/reports."""
    state = normalize_survival_state(_canonical_survival_seed(simulation_state))
    return {
        "enabled": bool(state.get("enabled", True)),
        "needs": {key: int(state.get(key, 0) or 0) for key in _NEED_KEYS},
        "last_turns": {key: state.get(key) for key in _LAST_TURN_KEYS},
        "event_count": len(state.get("events") or []),
        "source": SURVIVAL_PERSISTENCE_SOURCE,
    }
