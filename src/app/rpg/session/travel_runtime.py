from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.world.location_registry import (
    available_exits,
    current_location_id,
    get_location,
    resolve_exit_destination,
    set_current_location,
)
from app.rpg.world.world_event_log import add_world_event


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


TRAVEL_VERBS = (
    "go to ",
    "travel to ",
    "walk to ",
    "head to ",
    "move to ",
    "return to ",
    "follow bran",
    "follow the directions",
    "follow his directions",
    "follow bran's directions",
)


DIRECTIONS_ONLY_MARKERS = (
    "ask ",
    "ask bran",
    "directions",
    "where is",
    "where's",
    "how do i get",
    "how can i get",
    "can you point",
    "point me",
    "route to",
    "way to",
)


def _is_directions_only_request(player_input: str) -> bool:
    lower = _safe_str(player_input).strip().lower()
    if not lower:
        return False

    # Explicit follow/go/travel commands are movement, even if they mention
    # directions. Example: "I follow Bran's directions to the market".
    explicit_movement = (
        "follow " in lower
        or lower.startswith("go ")
        or " go to " in lower
        or "travel to " in lower
        or "walk to " in lower
        or "head to " in lower
        or "move to " in lower
        or "return to " in lower
    )
    if explicit_movement:
        return False

    return any(marker in lower for marker in DIRECTIONS_ONLY_MARKERS)


def detect_travel_destination_text(player_input: str) -> str:
    lower = _safe_str(player_input).strip().lower()
    if not lower:
        return ""

    if _is_directions_only_request(lower):
        return ""

    for verb in TRAVEL_VERBS:
        if verb in lower:
            remainder = lower.split(verb, 1)[1].strip(" .")
            if "market" in remainder:
                return "market"
            if "tavern" in remainder or "inn" in remainder or "rusty flagon" in remainder:
                return "tavern"
            if "old mill" in remainder or "mill road" in remainder:
                return "old mill road"
            return remainder

    # Allow short imperative movement forms, but not informational questions.
    if lower in {"market", "to market", "the market"}:
        return "market"
    if lower in {"tavern", "to tavern", "the tavern", "inn", "the inn"}:
        return "tavern"
    if lower in {"old mill", "old mill road", "to old mill", "to old mill road"}:
        return "old mill road"

    return ""


def resolve_travel_turn(
    *,
    player_input: str,
    simulation_state: Dict[str, Any],
    tick: int = 0,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    from_location_id = current_location_id(simulation_state)
    destination_text = detect_travel_destination_text(player_input)
    if not destination_text:
        return {"matched": False}

    destination_id = resolve_exit_destination(simulation_state, destination_text)
    if not destination_id:
        return {
            "matched": True,
            "applied": False,
            "status": "travel_destination_unavailable",
            "action_type": "travel",
            "from_location_id": from_location_id,
            "to_location_id": "",
            "destination_text": destination_text,
            "available_exits": available_exits(simulation_state),
            "summary": "No available route matches that destination.",
            "source": "deterministic_travel_runtime",
        }

    before = get_location(from_location_id)
    after = get_location(destination_id)
    set_current_location(simulation_state, destination_id)

    world_event = add_world_event(
        simulation_state,
        {
            "event_id": f"world:event:travel:{int(tick or 0)}:{from_location_id}:{destination_id}",
            "kind": "travel",
            "title": "Location changed",
            "summary": f"Travelled from {_safe_str(before.get('name')) or from_location_id} to {_safe_str(after.get('name')) or destination_id}.",
            "from_location_id": from_location_id,
            "to_location_id": destination_id,
            "tick": int(tick or 0),
            "source": "deterministic_travel_runtime",
        },
    )

    return {
        "matched": True,
        "applied": True,
        "status": "travelled",
        "action_type": "travel",
        "from_location_id": from_location_id,
        "to_location_id": destination_id,
        "from_location": before,
        "to_location": after,
        "destination_text": destination_text,
        "available_exits": available_exits(simulation_state),
        "present_npcs": deepcopy(after.get("present_npcs") or []),
        "world_event": world_event,
        "summary": f"You travel to {_safe_str(after.get('name')) or destination_id}.",
        "source": "deterministic_travel_runtime",
    }


def travel_resolved_result(travel_result: Dict[str, Any]) -> Dict[str, Any]:
    travel_result = _safe_dict(travel_result)
    if not travel_result.get("matched"):
        return {}
    return {
        "action_type": "travel",
        "outcome": "success" if travel_result.get("applied") else "failure",
        "travel_result": travel_result,
        "location_id": travel_result.get("to_location_id") or travel_result.get("from_location_id"),
        "summary": travel_result.get("summary"),
        "world_event": travel_result.get("world_event") or {},
        "source": "deterministic_travel_runtime",
    }
