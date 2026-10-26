"""A campaign's places, as its world says (roadmap §4.4): every campaign plays from a world, and the engine holds
no places of its own (A4)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str


def _world_locations(simulation_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The campaign's places: its world model's."""
    world_model = _safe_dict(_safe_dict(simulation_state).get("world_model"))
    return _safe_dict(world_model.get("locations"))


def get_location(location_id: str, simulation_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return deepcopy(_safe_dict(_world_locations(simulation_state).get(_safe_str(location_id))))


def default_location_id(simulation_state: dict[str, Any] | None = None) -> str:
    world_model = _safe_dict(_safe_dict(simulation_state).get("world_model"))
    return _safe_str(world_model.get("start_location_id"))


def current_location_id(simulation_state: dict[str, Any]) -> str:
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    location_id = (
        _safe_str(player_state.get("location_id"))
        or _safe_str(player_state.get("current_location_id"))
        or _safe_str(simulation_state.get("location_id"))
        or _safe_str(simulation_state.get("current_location_id"))
    )
    if not location_id:
        return default_location_id(simulation_state)
    if location_id in _world_locations(simulation_state):
        return location_id
    matched = find_location_by_name(location_id, simulation_state)
    return _safe_str(matched.get("location_id")) or location_id


def normalize_location_name(value: str) -> str:
    value = _safe_str(value).strip().lower()
    if value.startswith("location:"):
        value = value.split(":", 1)[1]
    value = value.replace("_", "-").replace("-", " ")
    value = value.replace("the ", "", 1) if value.startswith("the ") else value
    return " ".join(value.split())


def find_location_by_name(value: str, simulation_state: dict[str, Any] | None = None) -> dict[str, Any]:
    needle = normalize_location_name(value)
    if not needle:
        return {}
    locations = _world_locations(simulation_state)

    for location in locations.values():
        names = [
            _safe_str(location.get("location_id")),
            _safe_str(location.get("name")),
            _safe_str(location.get("short_name")),
            *_safe_list(location.get("aliases")),
        ]
        if any(normalize_location_name(name) == needle for name in names):
            return deepcopy(location)

    for location in locations.values():
        names = [
            _safe_str(location.get("name")),
            _safe_str(location.get("short_name")),
            *_safe_list(location.get("aliases")),
        ]
        if any(normalize_location_name(name) in needle for name in names):
            return deepcopy(location)

    return {}


def present_npcs_for_current_location(simulation_state: dict[str, Any]) -> list[dict[str, Any]]:
    location = get_location(current_location_id(simulation_state), simulation_state)
    return deepcopy(_safe_list(location.get("present_npcs")))
