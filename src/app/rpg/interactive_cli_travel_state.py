"""Deterministic short-session travel state for interactive RPG feature runs.

This helper is intentionally small and runtime-safe. It does not persist state
across sessions; it carries an explicit route/location view through an
interactive transcript so presentation and validation can report travel from
canonical state instead of hard-coded prose.

The route source is the campaign map state helper: initial sessions start from a
local-region seed, and outward edge-of-map requests append new locations/routes
to that canonical map before later turns can reference them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.interactive_cli_campaign_map_state import (
    OLD_MILL_LOCATION_ID,
    ROAD_LOCATION_ID,
    START_LOCATION_ID,
    campaign_map_location_name,
    ensure_campaign_map_state,
    initial_campaign_map_state,
    route_transition_for_command,
)

TRAVEL_STATE_SOURCE = "interactive_cli_travel_state_v1"
TRAVEL_STATE_PATCH = "phase_13_60_travel_state_foundation_v2"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _known_route_from_map(map_state: Mapping[str, Any]) -> list[str]:
    discovered = [
        _safe_str(location_id)
        for location_id in _safe_list(map_state.get("discovered_location_ids"))
        if _safe_str(location_id)
    ]
    return discovered or [START_LOCATION_ID, ROAD_LOCATION_ID, OLD_MILL_LOCATION_ID]


def _known_route_labels(map_state: Mapping[str, Any], route: list[str]) -> dict[str, str]:
    return {location_id: campaign_map_location_name(map_state, location_id) for location_id in route}


def initial_travel_state() -> dict[str, Any]:
    campaign_map_state = initial_campaign_map_state()
    known_route = _known_route_from_map(campaign_map_state)
    return {
        "source": TRAVEL_STATE_SOURCE,
        "patch": TRAVEL_STATE_PATCH,
        "current_location_id": START_LOCATION_ID,
        "current_location_name": campaign_map_location_name(campaign_map_state, START_LOCATION_ID),
        "previous_location_id": "",
        "previous_location_name": "",
        "destination_id": "",
        "destination_name": "",
        "direction": "",
        "known_route": known_route,
        "known_route_labels": _known_route_labels(campaign_map_state, known_route),
        "travel_history": [],
        "campaign_map_state": campaign_map_state,
    }


def advance_travel_state(previous_state: Mapping[str, Any] | None, command: str) -> dict[str, Any]:
    state = deepcopy(_safe_dict(previous_state)) if previous_state else initial_travel_state()
    if not state:
        state = initial_travel_state()

    previous_map_state = ensure_campaign_map_state(_safe_dict(state.get("campaign_map_state")))
    current_id = _safe_str(state.get("current_location_id") or START_LOCATION_ID)
    campaign_map_state, transition = route_transition_for_command(
        previous_map_state,
        current_location_id=current_id,
        command=command,
    )
    next_id = _safe_str(transition.get("to_location_id") or current_id)
    destination_id = _safe_str(transition.get("destination_id"))
    direction = _safe_str(transition.get("direction"))
    previous_id = current_id if next_id != current_id else _safe_str(state.get("previous_location_id"))

    history = list(_safe_list(state.get("travel_history")))
    history.append(
        {
            "command": command,
            "from_location_id": current_id,
            "from_location_name": campaign_map_location_name(campaign_map_state, current_id),
            "to_location_id": next_id,
            "to_location_name": campaign_map_location_name(campaign_map_state, next_id),
            "destination_id": destination_id,
            "destination_name": campaign_map_location_name(campaign_map_state, destination_id) if destination_id else "",
            "direction": direction,
            "map_expanded": bool(transition.get("map_expanded")),
        }
    )

    known_route = _known_route_from_map(campaign_map_state)
    updated = initial_travel_state()
    updated.update(
        {
            "patch": TRAVEL_STATE_PATCH,
            "current_location_id": next_id,
            "current_location_name": campaign_map_location_name(campaign_map_state, next_id),
            "previous_location_id": previous_id,
            "previous_location_name": campaign_map_location_name(campaign_map_state, previous_id) if previous_id else "",
            "destination_id": destination_id,
            "destination_name": campaign_map_location_name(campaign_map_state, destination_id) if destination_id else "",
            "direction": direction,
            "known_route": known_route,
            "known_route_labels": _known_route_labels(campaign_map_state, known_route),
            "travel_history": history,
            "campaign_map_state": campaign_map_state,
        }
    )
    return updated


def travel_requested_terms_for_state(state: Mapping[str, Any], command: str, existing_terms: list[Any] | None = None) -> list[str]:
    terms = [_safe_str(term).strip() for term in (existing_terms or []) if _safe_str(term).strip()]
    seen = {term.lower() for term in terms}
    text = command.lower()
    campaign_map_state = ensure_campaign_map_state(_safe_dict(state.get("campaign_map_state")))
    candidates = ["travel", "road", "map", "route"]
    for value in (
        state.get("current_location_name"),
        state.get("previous_location_name"),
        state.get("destination_name"),
        state.get("direction"),
    ):
        value_text = _safe_str(value).strip()
        if value_text:
            candidates.append(value_text)
    for location_id in _safe_list(state.get("known_route")):
        name = campaign_map_location_name(campaign_map_state, _safe_str(location_id)).strip()
        if name:
            candidates.append(name)
    for keyword in (
        "north",
        "south",
        "east",
        "tavern",
        "old mill",
        "leave",
        "continue",
        "back",
        "look",
        "around",
        "beyond",
        "river",
        "watchtower",
        "quarry",
    ):
        if keyword in text:
            candidates.append(keyword)
    for term in candidates:
        clean = _safe_str(term).strip()
        if clean and clean.lower() not in seen:
            terms.append(clean)
            seen.add(clean.lower())
    return terms
