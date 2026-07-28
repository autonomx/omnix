"""Deterministic typed regional-pressure propagation signatures."""
from __future__ import annotations

from typing import Any

_COMPONENTS = (
    "propagation_mode",
    "place_dimension",
    "place_operation",
    "actor_dimension",
    "actor_operation",
    "group_dimension",
    "group_operation",
    "magnitude_band",
    "onset_band",
    "duration_band",
    "recovery_mode",
)
_PLACE_EFFECTS = (
    ("market_price", "increase"),
    ("resource_supply", "decrease"),
    ("route_travel_time", "increase"),
    ("route_hazard", "increase"),
    ("information_delay", "increase"),
    ("public_order", "decrease"),
    ("service_availability", "disable"),
    ("market_price", "decrease"),
)
_ACTOR_EFFECTS = (
    ("next_action", "replace"),
    ("obligation_load", "increase"),
    ("location_access", "disable"),
    ("risk_exposure", "increase"),
    ("obligation_load", "decrease"),
    ("location_access", "enable"),
)
_GROUP_EFFECTS = (
    ("objective_priority", "increase"),
    ("resource_control", "decrease"),
    ("information_reach", "decrease"),
    ("response_capacity", "decrease"),
    ("objective_priority", "decrease"),
    ("resource_control", "increase"),
)
_MODES = (
    "route_borne",
    "market_borne",
    "institutional_response",
    "resource_shortage",
    "rumour_borne",
    "public_disorder",
)
_MAGNITUDES = ("minor", "moderate", "severe", "critical")
_ONSETS = ("same_tick", "next_tick", "one_day", "several_days")
_DURATIONS = ("one_tick", "several_ticks", "one_week", "until_recovery")
_RECOVERY = (
    "route_reopened",
    "reserve_restored",
    "agreement_reached",
    "authority_stabilised",
    "evidence_verified",
    "service_repaired",
)


def pressure_propagation_components() -> tuple[str, ...]:
    return _COMPONENTS


def deterministic_pressure_propagation_signature(index: int) -> dict[str, Any]:
    place_dimension, place_operation = _PLACE_EFFECTS[index % len(_PLACE_EFFECTS)]
    actor_dimension, actor_operation = _ACTOR_EFFECTS[(index * 5 + 1) % len(_ACTOR_EFFECTS)]
    group_dimension, group_operation = _GROUP_EFFECTS[(index * 3 + 2) % len(_GROUP_EFFECTS)]
    return {
        "propagation_mode": _MODES[index % len(_MODES)],
        "place_dimension": place_dimension,
        "place_operation": place_operation,
        "actor_dimension": actor_dimension,
        "actor_operation": actor_operation,
        "group_dimension": group_dimension,
        "group_operation": group_operation,
        "magnitude_band": _MAGNITUDES[(index * 3 + 1) % len(_MAGNITUDES)],
        "onset_band": _ONSETS[(index * 3 + 2) % len(_ONSETS)],
        "duration_band": _DURATIONS[(index * 3 + 1) % len(_DURATIONS)],
        "recovery_mode": _RECOVERY[(index * 5 + 3) % len(_RECOVERY)],
    }


__all__ = [
    "deterministic_pressure_propagation_signature",
    "pressure_propagation_components",
]
