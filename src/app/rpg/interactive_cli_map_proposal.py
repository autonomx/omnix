"""Deterministic map proposal protocol for interactive RPG feature runs.

LLM/world generation may draft map expansions, but runtime code must validate and
canonicalize those drafts before they become campaign-map truth.  This helper is
small and pure so later live-runtime integration can reuse the same acceptance,
repair, and fallback behavior without asking presentation text to own state.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from app.rpg.interactive_cli_campaign_map_state import (
    CAMPAIGN_MAP_STATE_SOURCE,
    campaign_map_location_name,
    ensure_campaign_map_state,
)

MAP_PROPOSAL_PROTOCOL_SOURCE = "interactive_cli_map_proposal_v1"
MAP_PROPOSAL_PROTOCOL_PATCH = "phase_13_70_map_proposal_protocol_v1"

_ALLOWED_DIRECTIONS = {"north", "south", "east", "west", "outward", "back"}
_DEFAULT_KIND = "landmark"
_DEFAULT_TAGS = ["new_region", "proposal"]
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_LOCATION_ID_PATTERN = re.compile(r"^location:[a-z0-9]+(?:-[a-z0-9]+)*$")


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _slugify(value: str, *, fallback: str = "unknown-location") -> str:
    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or fallback


def _location_id_from_name(name: str) -> str:
    return f"location:{_slugify(name)}"


def _direction_from_command(command: str) -> str:
    text = command.lower()
    for direction in ("north", "south", "east", "west"):
        if direction in text:
            return direction
    if any(term in text for term in ("beyond", "follow", "toward", "continue")):
        return "outward"
    return "outward"


def _reverse_direction(direction: str) -> str:
    return {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "outward": "back",
        "back": "outward",
    }.get(direction, "back")


def _clean_tags(value: Any) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in _safe_list(value):
        tag = _slugify(_safe_str(raw_tag), fallback="").replace("-", "_")
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= 8:
            break
    for fallback_tag in _DEFAULT_TAGS:
        if fallback_tag not in seen:
            tags.append(fallback_tag)
            seen.add(fallback_tag)
    return tags


def deterministic_map_proposal_fallback(command: str) -> dict[str, Any]:
    """Return a deterministic proposal when an LLM draft is missing or rejected."""

    text = command.lower()
    if "river" in text:
        name = "river town"
        kind = "settlement"
        tags = ["river", "settlement", "new_region"]
    elif "watchtower" in text or "tower" in text:
        name = "ruined watchtower"
        kind = "landmark"
        tags = ["ruin", "lookout", "new_region"]
    elif "quarry" in text:
        name = "old quarry"
        kind = "landmark"
        tags = ["quarry", "wilderness", "new_region"]
    else:
        name = "east road"
        kind = "road"
        tags = ["road", "wilderness_edge", "new_region"]
    return {
        "location": {
            "id": _location_id_from_name(name),
            "name": name,
            "kind": kind,
            "tags": tags,
        },
        "exit": {
            "direction": _direction_from_command(command),
            "reverse_direction": _reverse_direction(_direction_from_command(command)),
        },
    }


def canonicalize_map_proposal(
    proposal: Mapping[str, Any] | None,
    *,
    command: str,
    current_location_id: str,
) -> dict[str, Any]:
    """Validate and canonicalize a drafted map expansion proposal.

    The returned shape is safe to append to campaign map state. Invalid or absent
    proposals are rejected and replaced by deterministic fallback data. Malformed
    but useful proposals are repaired with explicit repair metadata.
    """

    repairs: list[str] = []
    rejected = not isinstance(proposal, Mapping)
    draft = _safe_dict(proposal)
    if rejected:
        draft = deterministic_map_proposal_fallback(command)
        repairs.append("proposal_replaced_with_deterministic_fallback")

    location = _safe_dict(draft.get("location"))
    exit_data = _safe_dict(draft.get("exit"))

    name = _safe_str(location.get("name")).strip()
    if not name:
        fallback_location = _safe_dict(deterministic_map_proposal_fallback(command).get("location"))
        name = _safe_str(fallback_location.get("name")).strip() or "east road"
        repairs.append("missing_location_name_repaired")

    location_id = _safe_str(location.get("id")).strip().lower()
    if not _LOCATION_ID_PATTERN.match(location_id):
        location_id = _location_id_from_name(name)
        repairs.append("invalid_location_id_repaired")

    kind = _slugify(_safe_str(location.get("kind")).strip(), fallback=_DEFAULT_KIND).replace("-", "_")
    tags = _clean_tags(location.get("tags"))

    from_location_id = _safe_str(exit_data.get("from_location_id")).strip() or current_location_id
    if from_location_id != current_location_id:
        from_location_id = current_location_id
        repairs.append("exit_from_location_repaired")

    direction = _safe_str(exit_data.get("direction")).strip().lower()
    if direction not in _ALLOWED_DIRECTIONS:
        direction = _direction_from_command(command)
        repairs.append("invalid_direction_repaired")

    reverse_direction = _safe_str(exit_data.get("reverse_direction")).strip().lower()
    if reverse_direction not in _ALLOWED_DIRECTIONS or reverse_direction == direction:
        reverse_direction = _reverse_direction(direction)
        repairs.append("reverse_direction_repaired")

    status = "rejected" if rejected else "repaired" if repairs else "accepted"
    return {
        "source": MAP_PROPOSAL_PROTOCOL_SOURCE,
        "patch": MAP_PROPOSAL_PROTOCOL_PATCH,
        "status": status,
        "repairs": repairs,
        "command": command,
        "location": {
            "id": location_id,
            "name": name,
            "kind": kind,
            "tags": tags,
        },
        "exit": {
            "from_location_id": from_location_id,
            "to_location_id": location_id,
            "direction": direction,
            "reverse_direction": reverse_direction,
            "travel_cost": 1,
        },
    }


def _has_edge(map_state: Mapping[str, Any], from_location_id: str, to_location_id: str) -> bool:
    for edge in _safe_list(map_state.get("edges")):
        edge_dict = _safe_dict(edge)
        if edge_dict.get("from_location_id") == from_location_id and edge_dict.get("to_location_id") == to_location_id:
            return True
        if edge_dict.get("from_location_id") == to_location_id and edge_dict.get("to_location_id") == from_location_id:
            return True
    return False


def apply_map_proposal_to_campaign_map(
    previous_map_state: Mapping[str, Any] | None,
    proposal: Mapping[str, Any] | None,
    *,
    command: str,
    current_location_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append a validated map proposal to canonical campaign map state."""

    map_state = ensure_campaign_map_state(deepcopy(_safe_dict(previous_map_state)))
    canonical = canonicalize_map_proposal(proposal, command=command, current_location_id=current_location_id)
    location = _safe_dict(canonical.get("location"))
    exit_data = _safe_dict(canonical.get("exit"))

    location_id = _safe_str(location.get("id"))
    locations = _safe_dict(map_state.setdefault("locations", {}))
    if location_id not in locations:
        locations[location_id] = {
            "id": location_id,
            "name": _safe_str(location.get("name")),
            "kind": _safe_str(location.get("kind")),
            "tags": list(_safe_list(location.get("tags"))),
            "discovered": True,
            "generated_from": MAP_PROPOSAL_PROTOCOL_SOURCE,
        }
    map_state["locations"] = locations

    discovered = list(_safe_list(map_state.setdefault("discovered_location_ids", [])))
    if location_id not in discovered:
        discovered.append(location_id)
    map_state["discovered_location_ids"] = discovered

    from_location_id = _safe_str(exit_data.get("from_location_id")) or current_location_id
    if not _has_edge(map_state, from_location_id, location_id):
        edges = list(_safe_list(map_state.setdefault("edges", [])))
        edges.append(
            {
                "from_location_id": from_location_id,
                "to_location_id": location_id,
                "direction": _safe_str(exit_data.get("direction")),
                "reverse_direction": _safe_str(exit_data.get("reverse_direction")),
                "travel_cost": int(exit_data.get("travel_cost") or 1),
                "discovered": True,
                "generated_from": MAP_PROPOSAL_PROTOCOL_SOURCE,
            }
        )
        map_state["edges"] = edges

    expansions = list(_safe_list(map_state.setdefault("expansions", [])))
    expansions.append(
        {
            "command": command,
            "from_location_id": from_location_id,
            "to_location_id": location_id,
            "to_location_name": campaign_map_location_name(map_state, location_id),
            "direction": _safe_str(exit_data.get("direction")),
            "policy": "canonicalize_llm_map_proposal",
            "proposal_status": _safe_str(canonical.get("status")),
            "proposal_repairs": list(_safe_list(canonical.get("repairs"))),
            "proposal_source": MAP_PROPOSAL_PROTOCOL_SOURCE,
        }
    )
    map_state["expansions"] = expansions
    map_state["last_map_proposal"] = canonical
    map_state["proposal_protocol_patch"] = MAP_PROPOSAL_PROTOCOL_PATCH

    transition = {
        "from_location_id": from_location_id,
        "from_location_name": campaign_map_location_name(map_state, from_location_id),
        "to_location_id": location_id,
        "to_location_name": campaign_map_location_name(map_state, location_id),
        "destination_id": location_id,
        "destination_name": campaign_map_location_name(map_state, location_id),
        "direction": _safe_str(exit_data.get("direction")),
        "map_expanded": True,
        "proposal_status": _safe_str(canonical.get("status")),
    }
    return map_state, transition
