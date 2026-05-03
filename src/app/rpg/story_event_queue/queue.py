from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.story_event_queue.state import (
    add_story_event_queue_history,
    ensure_story_event_queue_state,
)
from app.rpg.story_events.application import apply_story_event
from app.rpg.story_events.state import has_story_event_been_applied
from app.rpg.story_packs.definition_registries import get_story_event_definition

SAFE_QUEUE_PROCESS_MODES = {"idle", "wait", "listen", "observe", "world_tick", "__ambient_tick__"}
MAX_QUEUE_APPLICATIONS_PER_TICK = 3


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _stable_queue_id(
    *,
    event_id: str,
    source: str,
    due_turn: int,
    reason: str = "",
) -> str:
    payload = json.dumps(
        {
            "event_id": event_id,
            "source": source,
            "due_turn": int(due_turn or 0),
            "reason": reason,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"story_event_queue:{digest}"


def enqueue_story_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    source: str = "manual",
    enqueued_turn: int = 0,
    due_turn: int | None = None,
    delay_turns: int = 0,
    priority: int = 50,
    reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    event = dict(_safe_dict(event))
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return {"ok": False, "reason": "missing_event_id"}

    if has_story_event_been_applied(simulation_state, event_id):
        return {
            "ok": True,
            "reason": "already_applied",
            "event_id": event_id,
            "queued": False,
        }

    resolved_due_turn = int(due_turn if due_turn is not None else int(enqueued_turn or 0) + int(delay_turns or 0))
    queue_id = _stable_queue_id(
        event_id=event_id,
        source=source,
        due_turn=resolved_due_turn,
        reason=reason,
    )
    state = ensure_story_event_queue_state(simulation_state)
    pending = list(state.get("pending") or [])

    for row in pending:
        if row.get("queue_id") == queue_id or row.get("event_id") == event_id:
            return {
                "ok": True,
                "reason": "already_queued",
                "event_id": event_id,
                "queue_id": row.get("queue_id"),
                "queued": False,
                "item": row,
            }

    item = {
        "queue_id": queue_id,
        "event_id": event_id,
        "source": str(source or "manual"),
        "status": "pending",
        "enqueued_turn": int(enqueued_turn or 0),
        "due_turn": resolved_due_turn,
        "priority": max(0, min(100, int(priority or 50))),
        "reason": str(reason or ""),
        "event": event,
        "metadata": dict(metadata or {}),
    }
    pending.append(item)
    state["pending"] = pending
    simulation_state["story_event_queue_state"] = state
    ensure_story_event_queue_state(simulation_state)
    return {
        "ok": True,
        "reason": "queued",
        "queued": True,
        "event_id": event_id,
        "queue_id": queue_id,
        "item": item,
    }


def enqueue_story_event_definition(
    simulation_state: Dict[str, Any],
    event_id: str,
    *,
    source: str = "definition",
    enqueued_turn: int = 0,
    due_turn: int | None = None,
    delay_turns: int = 0,
    priority: int = 50,
    reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    event = get_story_event_definition(simulation_state, event_id)
    if not event:
        return {
            "ok": False,
            "reason": "story_event_definition_missing",
            "event_id": event_id,
        }
    return enqueue_story_event(
        simulation_state,
        event,
        source=source,
        enqueued_turn=enqueued_turn,
        due_turn=due_turn,
        delay_turns=delay_turns,
        priority=priority,
        reason=reason,
        metadata=metadata,
    )


def _is_due(item: Dict[str, Any], *, turn_index: int) -> bool:
    return int(item.get("due_turn") or 0) <= int(turn_index or 0)


def process_story_event_queue(
    simulation_state: Dict[str, Any],
    *,
    mode: str = "idle",
    turn_index: int = 0,
    max_applications: int = MAX_QUEUE_APPLICATIONS_PER_TICK,
) -> Dict[str, Any]:
    state = ensure_story_event_queue_state(simulation_state)
    mode = str(mode or "")
    if mode not in SAFE_QUEUE_PROCESS_MODES:
        return {
            "ok": True,
            "reason": "unsafe_mode",
            "mode": mode,
            "safe_modes": sorted(SAFE_QUEUE_PROCESS_MODES),
            "applied": [],
            "skipped": [],
            "remaining": list(state.get("pending") or []),
            "applied_count": 0,
        }

    pending = list(state.get("pending") or [])
    due_items = [row for row in pending if _is_due(row, turn_index=turn_index)]
    future_items = [row for row in pending if not _is_due(row, turn_index=turn_index)]
    due_items.sort(
        key=lambda row: (
            -int(row.get("priority") or 0),
            int(row.get("due_turn") or 0),
            str(row.get("queue_id") or ""),
        )
    )

    max_applications = max(0, min(MAX_QUEUE_APPLICATIONS_PER_TICK, int(max_applications or 0)))
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    remaining_due: List[Dict[str, Any]] = []

    for item in due_items:
        event_id = str(item.get("event_id") or "")
        queue_id = str(item.get("queue_id") or "")
        if len(applied) >= max_applications:
            remaining_due.append(item)
            skipped.append({"queue_id": queue_id, "event_id": event_id, "reason": "application_limit_reached"})
            continue

        if has_story_event_been_applied(simulation_state, event_id):
            result = {
                "ok": True,
                "reason": "already_applied",
                "event_id": event_id,
            }
            add_story_event_queue_history(
                simulation_state,
                queue_id=queue_id,
                event_id=event_id,
                status="skipped",
                processed_turn=turn_index,
                reason="already_applied",
                result=result,
            )
            skipped.append({"queue_id": queue_id, "event_id": event_id, "reason": "already_applied"})
            continue

        event = dict(_safe_dict(item.get("event")))
        result = apply_story_event(simulation_state, event, turn_index=turn_index)
        if result.get("ok"):
            applied.append(
                {
                    "queue_id": queue_id,
                    "event_id": event_id,
                    "result": result,
                }
            )
            add_story_event_queue_history(
                simulation_state,
                queue_id=queue_id,
                event_id=event_id,
                status="applied",
                processed_turn=turn_index,
                reason=result.get("reason") or "applied",
                result=result,
            )
        else:
            skipped.append(
                {
                    "queue_id": queue_id,
                    "event_id": event_id,
                    "reason": "apply_failed",
                    "result": result,
                }
            )
            add_story_event_queue_history(
                simulation_state,
                queue_id=queue_id,
                event_id=event_id,
                status="failed",
                processed_turn=turn_index,
                reason=result.get("reason") or "apply_failed",
                result=result,
            )

    state = ensure_story_event_queue_state(simulation_state)
    state["pending"] = future_items + remaining_due
    simulation_state["story_event_queue_state"] = state
    ensure_story_event_queue_state(simulation_state)
    final_state = ensure_story_event_queue_state(simulation_state)
    return {
        "ok": True,
        "reason": "processed",
        "mode": mode,
        "turn_index": int(turn_index or 0),
        "due_count": len(due_items),
        "applied": applied,
        "applied_count": len(applied),
        "skipped": skipped,
        "pending_count": len(final_state.get("pending") or []),
        "remaining": list(final_state.get("pending") or []),
    }