from __future__ import annotations

from typing import Any, Dict, List


MAX_PENDING_STORY_EVENTS = 200
MAX_STORY_EVENT_QUEUE_HISTORY = 300


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def normalize_story_event_queue_item(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "queue_id": _safe_str(value.get("queue_id")),
        "event_id": _safe_str(value.get("event_id")),
        "source": _safe_str(value.get("source")) or "unknown",
        "status": _safe_str(value.get("status")) or "pending",
        "enqueued_turn": _safe_int(value.get("enqueued_turn"), 0),
        "due_turn": _safe_int(value.get("due_turn"), 0),
        "priority": max(0, min(100, _safe_int(value.get("priority"), 50))),
        "reason": _safe_str(value.get("reason")),
        "event": dict(_safe_dict(value.get("event"))),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_event_queue_history_item(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "queue_id": _safe_str(value.get("queue_id")),
        "event_id": _safe_str(value.get("event_id")),
        "status": _safe_str(value.get("status")) or "unknown",
        "processed_turn": _safe_int(value.get("processed_turn"), 0),
        "reason": _safe_str(value.get("reason")),
        "result": dict(_safe_dict(value.get("result"))),
    }


def normalize_story_event_queue_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    pending = [
        normalize_story_event_queue_item(row)
        for row in _safe_list(value.get("pending"))
        if isinstance(row, dict)
    ]
    pending = [
        row
        for row in pending
        if row.get("queue_id") and row.get("event_id") and row.get("status") == "pending"
    ][-MAX_PENDING_STORY_EVENTS:]
    pending.sort(
        key=lambda row: (
            int(row.get("due_turn") or 0),
            -int(row.get("priority") or 0),
            str(row.get("queue_id") or ""),
        )
    )

    history = [
        normalize_story_event_queue_history_item(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_STORY_EVENT_QUEUE_HISTORY:]

    return {
        "version": 1,
        "pending": pending,
        "history": history,
        "max_pending": MAX_PENDING_STORY_EVENTS,
        "max_history": MAX_STORY_EVENT_QUEUE_HISTORY,
    }


def ensure_story_event_queue_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_event_queue_state(simulation_state.get("story_event_queue_state"))
    simulation_state["story_event_queue_state"] = state
    return state


def add_story_event_queue_history(
    simulation_state: Dict[str, Any],
    *,
    queue_id: str,
    event_id: str,
    status: str,
    processed_turn: int,
    reason: str = "",
    result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_story_event_queue_state(simulation_state)
    row = normalize_story_event_queue_history_item(
        {
            "queue_id": queue_id,
            "event_id": event_id,
            "status": status,
            "processed_turn": processed_turn,
            "reason": reason,
            "result": result or {},
        }
    )
    history = list(state.get("history") or [])
    history.append(row)
    state["history"] = history[-MAX_STORY_EVENT_QUEUE_HISTORY:]
    simulation_state["story_event_queue_state"] = normalize_story_event_queue_state(state)
    return {
        "ok": True,
        "reason": "queue_history_recorded",
        "history_item": row,
    }