"""Bundle BE — canonical survival save/load normalization.

The BA runtime state lives at ``simulation_state['survival']``.  This module is
used by session save/load/export/import boundaries so malformed, legacy, or
LLM-expanded survival payloads cannot become persistent truth.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, Tuple

from app.apps.rpg.survival import SURVIVAL_STATE_KEY, normalize_survival_state
from app.apps.rpg.safe_values import mapping_copy as _safe_dict

SURVIVAL_PERSISTENCE_SOURCE = "runtime_survival_persistence"

_NEED_KEYS: Tuple[str, str, str] = ("hunger", "thirst", "fatigue")
_LAST_TURN_KEYS: Tuple[str, str, str] = (
    "last_food_turn",
    "last_water_turn",
    "last_rest_turn",
)


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
    normalized = deepcopy(_safe_dict(simulation_state))
    state = normalize_survival_state(_canonical_survival_seed(normalized))
    normalized[SURVIVAL_STATE_KEY] = state
    return normalized


def normalize_session_survival_for_persistence(session: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a whole session at save/load/export/import boundaries."""
    normalized_session = deepcopy(_safe_dict(session))
    simulation_state = normalize_survival_for_persistence(
        _safe_dict(normalized_session.get("simulation_state"))
    )
    normalized_session["simulation_state"] = simulation_state
    return normalized_session


