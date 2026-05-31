from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm_text(value: Any) -> str:
    return " ".join(_safe_str(value).lower().strip().split())


def _set_location(state: Dict[str, Any], *, location_id: str, name: str, reason: str, turn_index: int) -> None:
    state = _safe_dict(state)
    previous = _safe_str(
        state.get("current_location")
        or _safe_dict(state.get("scene")).get("location")
        or _safe_dict(state.get("location")).get("name")
    )
    state["current_location"] = location_id
    state["current_location_name"] = name
    scene = state.setdefault("scene", {})
    if isinstance(scene, dict):
        scene["location"] = name
        scene["location_id"] = location_id
    history = state.setdefault("location_history", [])
    if isinstance(history, list):
        if not history or _safe_dict(history[-1]).get("location_id") != location_id:
            history.append(
                {
                    "turn": int(turn_index or 0),
                    "location_id": location_id,
                    "name": name,
                    "previous": previous,
                    "reason": reason,
                }
            )

def apply_autoplay_travel_authority(
    simulation_state: Dict[str, Any],
    *,
    player_action: str,
    turn_index: int,
) -> Dict[str, Any]:
    """Apply bounded deterministic travel when the player uses clear travel verbs.

    This is not LLM mutation. It only recognizes concrete movement commands that
    the autoplay harness itself is generating.
    """
    state = _safe_dict(simulation_state)
    lower = _norm_text(player_action)
    changed = False
    events: List[Dict[str, Any]] = []

    if any(
        phrase in lower
        for phrase in (
            "leave the rusty flagon",
            "leave the tavern",
            "follow the road outside",
            "road outside",
            "follow the road trail",
            "travel toward the road",
            "toward the main road",
            "follow the bandit road trail",
        )
    ):
        _set_location(
            state,
            location_id="location:east_road_outside_tavern",
            name="East Road outside the Rusty Flagon",
            reason="autoplay_travel_authority:road_outside_tavern",
            turn_index=turn_index,
        )
        changed = True
        events.append(
            {
                "turn": int(turn_index or 0),
                "type": "travel",
                "location_id": "location:east_road_outside_tavern",
                "summary": "The player left the tavern and followed the road outside.",
            }
        )

    if any(
        phrase in lower
        for phrase in (
            "mill bridge",
            "old east road",
            "bridge watchers",
            "toward the bridge",
        )
    ):
        _set_location(
            state,
            location_id="location:mill_bridge_road",
            name="Road to the Mill Bridge",
            reason="autoplay_travel_authority:mill_bridge_road",
            turn_index=turn_index,
        )
        changed = True
        events.append(
            {
                "turn": int(turn_index or 0),
                "type": "travel",
                "location_id": "location:mill_bridge_road",
                "summary": "The player followed the lead toward the Mill Bridge road.",
            }
        )

    if events:
        world_events = state.setdefault("world_events", [])
        if isinstance(world_events, list):
            world_events.extend(events)
        recent = state.setdefault("recent_world_events", [])
        if isinstance(recent, list):
            recent.extend(events)
            del recent[:-20]

    return {"changed": changed, "events": events, "simulation_state": state}
