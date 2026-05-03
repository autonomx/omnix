from __future__ import annotations

from typing import Any, Dict, List


MAX_APPLIED_STORY_EVENTS = 500


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_applied_story_event(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "event_id": _safe_str(value.get("event_id")),
        "arc_id": _safe_str(value.get("arc_id")),
        "kind": _safe_str(value.get("kind")) or "event",
        "summary": _safe_str(value.get("summary")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "effect_results": [
            dict(row)
            for row in _safe_list(value.get("effect_results"))
            if isinstance(row, dict)
        ][:50],
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_event_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    applied_events: Dict[str, Dict[str, Any]] = {}
    for event_id, row in _safe_dict(value.get("applied_events")).items():
        event_id = str(event_id or "")
        if not event_id:
            continue
        applied_events[event_id] = normalize_applied_story_event(
            dict(row, event_id=event_id)
        )
    ordered_ids = sorted(
        applied_events,
        key=lambda eid: (
            int(applied_events[eid].get("turn_index") or 0),
            eid,
        ),
    )[-MAX_APPLIED_STORY_EVENTS:]
    return {
        "version": 1,
        "applied_events": {event_id: applied_events[event_id] for event_id in ordered_ids},
        "max_applied_events": MAX_APPLIED_STORY_EVENTS,
    }


def ensure_story_event_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_event_state(simulation_state.get("story_event_state"))
    simulation_state["story_event_state"] = state
    return state


def has_story_event_been_applied(simulation_state: Dict[str, Any], event_id: str) -> bool:
    state = ensure_story_event_state(simulation_state)
    return event_id in state.get("applied_events", {})


def get_applied_story_event(
    simulation_state: Dict[str, Any],
    event_id: str,
) -> Dict[str, Any] | None:
    state = ensure_story_event_state(simulation_state)
    return state.get("applied_events", {}).get(event_id)


def mark_story_event_applied(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    effect_results: List[Dict[str, Any]],
    turn_index: int = 0,
) -> Dict[str, Any]:
    state = ensure_story_event_state(simulation_state)
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return {"ok": False, "reason": "missing_event_id"}
    applied = normalize_applied_story_event(
        {
            "event_id": event_id,
            "arc_id": event.get("arc_id") or "",
            "kind": event.get("kind") or "event",
            "summary": event.get("summary") or "",
            "turn_index": turn_index,
            "effect_results": effect_results,
            "metadata": {"participants": list(event.get("participants") or [])[:20]},
        }
    )
    state.setdefault("applied_events", {})[event_id] = applied
    # Re-normalize to enforce bounds.
    simulation_state["story_event_state"] = normalize_story_event_state(state)
    return {
        "ok": True,
        "reason": "applied_marked",
        "event_id": event_id,
        "applied": simulation_state["story_event_state"]["applied_events"][event_id],
    }