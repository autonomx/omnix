"""Portable package compatibility for authoritative RPG map session state."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.rpg.map_release import persisted_map_state

_PACKAGE_MAP_KEY = "_rpg_map_state_v1"


def attach_map_state_to_package(
    package_payload: Mapping[str, object],
    session: Mapping[str, object],
) -> dict[str, Any]:
    """Embed deterministic map state in the package's accepted simulation group."""

    package = deepcopy(dict(package_payload))
    map_state = persisted_map_state(session)
    if not map_state:
        return package
    simulation_state = package.get("simulation_state")
    if not isinstance(simulation_state, dict):
        simulation_state = {}
    simulation_state[_PACKAGE_MAP_KEY] = map_state
    package["simulation_state"] = simulation_state
    return package


def restore_map_state_from_package(
    session: Mapping[str, object],
    package_payload: Mapping[str, object],
) -> dict[str, Any]:
    """Restore packaged map state without inferring IDs from display labels."""

    restored = deepcopy(dict(session))
    simulation_state = package_payload.get("simulation_state")
    packaged = simulation_state.get(_PACKAGE_MAP_KEY) if isinstance(simulation_state, Mapping) else None
    if not isinstance(packaged, Mapping):
        return restored

    state = restored.get("state")
    if not isinstance(state, dict):
        state = {}
    map_state = deepcopy(dict(packaged))
    state["map_state"] = map_state
    current_location_id = str(map_state.get("current_location_id") or "").strip()
    if current_location_id:
        state["current_location_id"] = current_location_id
        player = state.get("player")
        if not isinstance(player, dict):
            player = {}
        player["location_id"] = current_location_id
        state["player"] = player
    restored["state"] = state
    return restored


def packaged_map_state(package_payload: Mapping[str, object]) -> dict[str, object]:
    simulation_state = package_payload.get("simulation_state")
    value = simulation_state.get(_PACKAGE_MAP_KEY) if isinstance(simulation_state, Mapping) else None
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
