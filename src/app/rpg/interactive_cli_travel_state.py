"""Deterministic short-session travel state for interactive RPG feature runs.

This helper is intentionally small and runtime-safe. It does not mutate the
simulation world graph or persist state across sessions; it only carries an
explicit route/location view through an interactive transcript so presentation
and validation can report travel from state instead of from hard-coded prose.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

START_LOCATION_ID = "location:tavern"
START_LOCATION_NAME = "tavern"
ROAD_LOCATION_ID = "location:road-north"
ROAD_LOCATION_NAME = "north road"
OLD_MILL_LOCATION_ID = "location:old-mill"
OLD_MILL_LOCATION_NAME = "old mill"

TRAVEL_STATE_SOURCE = "interactive_cli_travel_state_v1"
TRAVEL_STATE_PATCH = "phase_13_60_travel_state_foundation_v1"

KNOWN_ROUTE = [
    START_LOCATION_ID,
    ROAD_LOCATION_ID,
    OLD_MILL_LOCATION_ID,
]
KNOWN_ROUTE_LABELS = {
    START_LOCATION_ID: START_LOCATION_NAME,
    ROAD_LOCATION_ID: ROAD_LOCATION_NAME,
    OLD_MILL_LOCATION_ID: OLD_MILL_LOCATION_NAME,
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def initial_travel_state() -> dict[str, Any]:
    return {
        "source": TRAVEL_STATE_SOURCE,
        "patch": TRAVEL_STATE_PATCH,
        "current_location_id": START_LOCATION_ID,
        "current_location_name": START_LOCATION_NAME,
        "previous_location_id": "",
        "previous_location_name": "",
        "destination_id": "",
        "destination_name": "",
        "direction": "",
        "known_route": list(KNOWN_ROUTE),
        "known_route_labels": dict(KNOWN_ROUTE_LABELS),
        "travel_history": [],
    }


def _route_index(location_id: str) -> int:
    try:
        return KNOWN_ROUTE.index(location_id)
    except ValueError:
        return 0


def _location_name(location_id: str) -> str:
    return KNOWN_ROUTE_LABELS.get(location_id, location_id.replace("location:", ""))


def _transition_for_command(command: str, current_location_id: str) -> tuple[str, str, str]:
    """Return (next_location_id, destination_id, direction)."""

    text = command.lower()
    if "old mill" in text or " mill" in text:
        return OLD_MILL_LOCATION_ID, OLD_MILL_LOCATION_ID, "north"
    if "look" in text and current_location_id == OLD_MILL_LOCATION_ID:
        return OLD_MILL_LOCATION_ID, OLD_MILL_LOCATION_ID, "around"
    if "south" in text or "back" in text or "tavern" in text:
        return START_LOCATION_ID, START_LOCATION_ID, "south"
    if "north" in text or "road" in text or "leave" in text:
        return ROAD_LOCATION_ID, ROAD_LOCATION_ID, "north"
    return current_location_id, "", ""


def advance_travel_state(previous_state: Mapping[str, Any] | None, command: str) -> dict[str, Any]:
    state = deepcopy(_safe_dict(previous_state)) if previous_state else initial_travel_state()
    if not state:
        state = initial_travel_state()

    current_id = _safe_str(state.get("current_location_id") or START_LOCATION_ID)
    next_id, destination_id, direction = _transition_for_command(command, current_id)
    previous_id = current_id if next_id != current_id else _safe_str(state.get("previous_location_id"))

    history = list(_safe_list(state.get("travel_history")))
    history.append(
        {
            "command": command,
            "from_location_id": current_id,
            "from_location_name": _location_name(current_id),
            "to_location_id": next_id,
            "to_location_name": _location_name(next_id),
            "destination_id": destination_id,
            "destination_name": _location_name(destination_id) if destination_id else "",
            "direction": direction,
        }
    )

    updated = initial_travel_state()
    updated.update(
        {
            "current_location_id": next_id,
            "current_location_name": _location_name(next_id),
            "previous_location_id": previous_id,
            "previous_location_name": _location_name(previous_id) if previous_id else "",
            "destination_id": destination_id,
            "destination_name": _location_name(destination_id) if destination_id else "",
            "direction": direction,
            "travel_history": history,
        }
    )
    return updated


def travel_requested_terms_for_state(state: Mapping[str, Any], command: str, existing_terms: list[Any] | None = None) -> list[str]:
    terms = [_safe_str(term).strip() for term in (existing_terms or []) if _safe_str(term).strip()]
    seen = {term.lower() for term in terms}
    text = command.lower()
    candidates = ["travel", "road"]
    for value in (
        state.get("current_location_name"),
        state.get("previous_location_name"),
        state.get("destination_name"),
        state.get("direction"),
    ):
        value_text = _safe_str(value).strip()
        if value_text:
            candidates.append(value_text)
    for keyword in ("north", "south", "tavern", "old mill", "leave", "continue", "back", "look", "around"):
        if keyword in text:
            candidates.append(keyword)
    for term in candidates:
        clean = _safe_str(term).strip()
        if clean and clean.lower() not in seen:
            terms.append(clean)
            seen.add(clean.lower())
    return terms
