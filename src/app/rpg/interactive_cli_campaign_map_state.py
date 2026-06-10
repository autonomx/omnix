"""Deterministic campaign map state for interactive RPG feature runs.

The live game can ask an LLM to draft or extend the world, but runtime code must
canonicalize that draft before it becomes truth.  This helper provides the small
canonical shape used by interactive feature runs: an initial local-region seed and
an append-only expansion path for edge-of-map travel requests.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

CAMPAIGN_MAP_STATE_SOURCE = "interactive_cli_campaign_map_state_v1"
CAMPAIGN_MAP_STATE_PATCH = "phase_13_60_campaign_map_state_foundation_v1"

START_LOCATION_ID = "location:tavern"
START_LOCATION_NAME = "tavern"
ROAD_LOCATION_ID = "location:road-north"
ROAD_LOCATION_NAME = "north road"
OLD_MILL_LOCATION_ID = "location:old-mill"
OLD_MILL_LOCATION_NAME = "old mill"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def initial_campaign_map_state() -> dict[str, Any]:
    """Return the canonical local-region seed for a new interactive campaign."""

    return {
        "source": CAMPAIGN_MAP_STATE_SOURCE,
        "patch": CAMPAIGN_MAP_STATE_PATCH,
        "seed_scope": "local_region_seed",
        "expansion_policy": "append_on_edge_request",
        "locations": {
            START_LOCATION_ID: {
                "id": START_LOCATION_ID,
                "name": START_LOCATION_NAME,
                "kind": "tavern",
                "tags": ["settlement", "safe", "service"],
                "discovered": True,
            },
            ROAD_LOCATION_ID: {
                "id": ROAD_LOCATION_ID,
                "name": ROAD_LOCATION_NAME,
                "kind": "road",
                "tags": ["road", "wilderness_edge"],
                "discovered": True,
            },
            OLD_MILL_LOCATION_ID: {
                "id": OLD_MILL_LOCATION_ID,
                "name": OLD_MILL_LOCATION_NAME,
                "kind": "landmark",
                "tags": ["ruin", "quest_hook", "wilderness"],
                "discovered": True,
            },
        },
        "edges": [
            {
                "from_location_id": START_LOCATION_ID,
                "to_location_id": ROAD_LOCATION_ID,
                "direction": "north",
                "reverse_direction": "south",
                "travel_cost": 1,
                "discovered": True,
            },
            {
                "from_location_id": ROAD_LOCATION_ID,
                "to_location_id": OLD_MILL_LOCATION_ID,
                "direction": "north",
                "reverse_direction": "south",
                "travel_cost": 1,
                "discovered": True,
            },
        ],
        "discovered_location_ids": [START_LOCATION_ID, ROAD_LOCATION_ID, OLD_MILL_LOCATION_ID],
        "expansions": [],
    }


def ensure_campaign_map_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    state = deepcopy(_safe_dict(value)) if value else initial_campaign_map_state()
    if not state:
        state = initial_campaign_map_state()
    state.setdefault("source", CAMPAIGN_MAP_STATE_SOURCE)
    state.setdefault("patch", CAMPAIGN_MAP_STATE_PATCH)
    state.setdefault("seed_scope", "local_region_seed")
    state.setdefault("expansion_policy", "append_on_edge_request")
    state.setdefault("locations", {})
    state.setdefault("edges", [])
    state.setdefault("discovered_location_ids", [])
    state.setdefault("expansions", [])
    return state


def campaign_map_location_name(map_state: Mapping[str, Any], location_id: str) -> str:
    locations = _safe_dict(map_state.get("locations"))
    location = _safe_dict(locations.get(location_id))
    name = _safe_str(location.get("name")).strip()
    return name or location_id.replace("location:", "").replace("-", " ")


def _has_edge(map_state: Mapping[str, Any], from_location_id: str, to_location_id: str) -> bool:
    for edge in _safe_list(map_state.get("edges")):
        edge_dict = _safe_dict(edge)
        if edge_dict.get("from_location_id") == from_location_id and edge_dict.get("to_location_id") == to_location_id:
            return True
        if edge_dict.get("from_location_id") == to_location_id and edge_dict.get("to_location_id") == from_location_id:
            return True
    return False


def _append_location(map_state: dict[str, Any], *, location_id: str, name: str, kind: str, tags: list[str]) -> None:
    locations = _safe_dict(map_state.setdefault("locations", {}))
    if location_id not in locations:
        locations[location_id] = {
            "id": location_id,
            "name": name,
            "kind": kind,
            "tags": tags,
            "discovered": True,
            "generated_from": CAMPAIGN_MAP_STATE_SOURCE,
        }
    discovered = list(_safe_list(map_state.setdefault("discovered_location_ids", [])))
    if location_id not in discovered:
        discovered.append(location_id)
    map_state["discovered_location_ids"] = discovered


def _append_edge(map_state: dict[str, Any], *, from_location_id: str, to_location_id: str, direction: str) -> None:
    if _has_edge(map_state, from_location_id, to_location_id):
        return
    reverse = "west" if direction == "east" else "south" if direction == "north" else "back"
    edges = list(_safe_list(map_state.setdefault("edges", [])))
    edges.append(
        {
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "direction": direction,
            "reverse_direction": reverse,
            "travel_cost": 1,
            "discovered": True,
            "generated_from": CAMPAIGN_MAP_STATE_SOURCE,
        }
    )
    map_state["edges"] = edges


def _expansion_for_command(command: str) -> tuple[str, str, str, list[str]]:
    text = command.lower()
    if "river" in text:
        return "location:river-town", "river town", "settlement", ["river", "settlement", "new_region"]
    if "watchtower" in text or "tower" in text:
        return "location:ruined-watchtower", "ruined watchtower", "landmark", ["ruin", "lookout", "new_region"]
    if "quarry" in text:
        return "location:old-quarry", "old quarry", "landmark", ["quarry", "wilderness", "new_region"]
    return "location:east-road", "east road", "road", ["road", "wilderness_edge", "new_region"]


def _requests_known_route_north(text: str) -> bool:
    return any(term in text for term in ("north", "road", "leave"))


def _requests_return_to_tavern(text: str) -> bool:
    return "south" in text or "back" in text or "toward the tavern" in text or "return to the tavern" in text


def _requests_map_expansion(text: str) -> bool:
    outward_terms = ("east", "beyond", "river", "watchtower", "tower", "quarry")
    if any(term in text for term in outward_terms):
        return True
    return "follow" in text and not any(term in text for term in ("old mill", "tavern", "north"))


def route_transition_for_command(
    previous_map_state: Mapping[str, Any] | None,
    *,
    current_location_id: str,
    command: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return updated canonical map state plus deterministic travel transition.

    Unknown outward travel requests append a new location/edge to the map.  The
    resulting map is then the canonical source of truth for later turns.
    """

    map_state = ensure_campaign_map_state(previous_map_state)
    text = command.lower()
    destination_id = ""
    direction = ""
    expanded = False

    if "look" in text and current_location_id == OLD_MILL_LOCATION_ID:
        destination_id = current_location_id
        direction = "around"
    elif "old mill" in text or " mill" in text:
        destination_id = OLD_MILL_LOCATION_ID
        direction = "north"
    elif _requests_return_to_tavern(text):
        destination_id = START_LOCATION_ID
        direction = "south"
    elif _requests_map_expansion(text):
        destination_id, name, kind, tags = _expansion_for_command(command)
        direction = "east" if "east" in text or "river" in text or "watchtower" in text else "outward"
        _append_location(map_state, location_id=destination_id, name=name, kind=kind, tags=tags)
        _append_edge(map_state, from_location_id=current_location_id, to_location_id=destination_id, direction=direction)
        expansions = list(_safe_list(map_state.setdefault("expansions", [])))
        expansions.append(
            {
                "command": command,
                "from_location_id": current_location_id,
                "to_location_id": destination_id,
                "to_location_name": campaign_map_location_name(map_state, destination_id),
                "direction": direction,
                "policy": "append_on_edge_request",
            }
        )
        map_state["expansions"] = expansions
        expanded = True
    elif _requests_known_route_north(text):
        destination_id = ROAD_LOCATION_ID
        direction = "north"
    else:
        destination_id = current_location_id
        direction = ""

    transition = {
        "from_location_id": current_location_id,
        "from_location_name": campaign_map_location_name(map_state, current_location_id),
        "to_location_id": destination_id or current_location_id,
        "to_location_name": campaign_map_location_name(map_state, destination_id or current_location_id),
        "destination_id": destination_id,
        "destination_name": campaign_map_location_name(map_state, destination_id) if destination_id else "",
        "direction": direction,
        "map_expanded": expanded,
    }
    return map_state, transition
