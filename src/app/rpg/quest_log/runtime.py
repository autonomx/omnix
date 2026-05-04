from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.quest_log.state import (
    MAX_PINNED_OBJECTIVES,
    append_quest_log_history,
    ensure_quest_log_state,
)
from app.rpg.story_arcs.milestones import build_story_objective_projection

MAX_QUEST_LOG_OBJECTIVES = 50
MAX_OBJECTIVE_TRACKER_ITEMS = 8


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _objective_sort_key(row: Dict[str, Any], pinned_ids: List[str]):
    objective_id = str(row.get("objective_id") or row.get("milestone_id") or "")
    pinned_index = pinned_ids.index(objective_id) if objective_id in pinned_ids else 9999
    return (
        pinned_index,
        objective_id not in pinned_ids,
        -int(row.get("priority") or 0),
        str(row.get("arc_id") or ""),
        str(row.get("title") or ""),
        objective_id,
    )


def _normalize_objective_row(row: Dict[str, Any], *, pinned_ids: List[str]) -> Dict[str, Any]:
    row = _safe_dict(row)
    objective_id = str(row.get("objective_id") or row.get("milestone_id") or "")
    return {
        "objective_id": objective_id,
        "milestone_id": str(row.get("milestone_id") or objective_id),
        "arc_id": str(row.get("arc_id") or ""),
        "quest_id": str(row.get("quest_id") or ""),
        "title": str(row.get("title") or row.get("objective_text") or objective_id),
        "objective_text": str(row.get("objective_text") or row.get("title") or objective_id),
        "status": str(row.get("status") or "active"),
        "priority": int(row.get("priority") or 0),
        "pinned": objective_id in pinned_ids,
    }


def _group_objectives_by_quest(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for row in objectives:
        quest_id = str(row.get("quest_id") or row.get("arc_id") or "story")
        group = groups.setdefault(
            quest_id,
            {
                "quest_id": quest_id,
                "title": quest_id.replace("_", " ").replace(":", " ").title(),
                "active_objectives": [],
                "completed_objectives": [],
            },
        )
        if row.get("status") == "completed":
            group["completed_objectives"].append(row)
        else:
            group["active_objectives"].append(row)
    out = list(groups.values())
    out.sort(
        key=lambda group: (
            not bool(group.get("active_objectives")),
            str(group.get("quest_id") or ""),
        )
    )
    return out


def build_quest_log_payload(
    simulation_state: Dict[str, Any],
    *,
    limit: int = MAX_QUEST_LOG_OBJECTIVES,
) -> Dict[str, Any]:
    limit = max(0, min(MAX_QUEST_LOG_OBJECTIVES, int(limit or MAX_QUEST_LOG_OBJECTIVES)))
    state = ensure_quest_log_state(simulation_state)
    pinned_ids = list(state.get("pinned_objective_ids") or [])
    projection = build_story_objective_projection(simulation_state, limit=limit)

    active = [
        _normalize_objective_row(row, pinned_ids=pinned_ids)
        for row in _safe_list(projection.get("active_objectives"))
        if isinstance(row, dict)
    ]
    completed = [
        _normalize_objective_row(row, pinned_ids=pinned_ids)
        for row in _safe_list(projection.get("completed_milestones"))
        if isinstance(row, dict)
    ]
    active.sort(key=lambda row: _objective_sort_key(row, pinned_ids))
    completed.sort(key=lambda row: (str(row.get("arc_id") or ""), str(row.get("objective_id") or "")))

    active = active[:limit]
    completed = completed[:limit]
    groups = _group_objectives_by_quest(active + completed)

    return {
        "ok": True,
        "format_version": "quest_log_v1",
        "pinned_objective_ids": pinned_ids,
        "active_objectives": active,
        "completed_objectives": completed,
        "quest_groups": groups[:limit],
        "history": list(state.get("history") or [])[-limit:],
        "actions": {
            "payload": "/api/rpg/quest_log/payload",
            "tracker": "/api/rpg/quest_log/tracker",
            "pin": "/api/rpg/quest_log/pin",
            "unpin": "/api/rpg/quest_log/unpin",
        },
        "rules": [
            "Quest log is derived from deterministic milestone state.",
            "Pinning only changes display preference.",
            "The UI cannot create or complete objectives.",
        ],
        "bounded": {
            "limit": limit,
            "max_objectives": MAX_QUEST_LOG_OBJECTIVES,
            "max_pinned_objectives": MAX_PINNED_OBJECTIVES,
        },
    }


def build_objective_tracker_payload(
    simulation_state: Dict[str, Any],
    *,
    limit: int = MAX_OBJECTIVE_TRACKER_ITEMS,
) -> Dict[str, Any]:
    limit = max(0, min(MAX_OBJECTIVE_TRACKER_ITEMS, int(limit or MAX_OBJECTIVE_TRACKER_ITEMS)))
    quest_log = build_quest_log_payload(simulation_state, limit=MAX_QUEST_LOG_OBJECTIVES)
    active = list(quest_log.get("active_objectives") or [])
    pinned = [row for row in active if row.get("pinned")]
    unpinned = [row for row in active if not row.get("pinned")]
    tracker = (pinned + unpinned)[:limit]
    return {
        "ok": True,
        "format_version": "objective_tracker_v1",
        "objectives": tracker,
        "pinned_objective_ids": list(quest_log.get("pinned_objective_ids") or []),
        "active_count": len(active),
        "completed_count": len(quest_log.get("completed_objectives") or []),
        "bounded": {
            "limit": limit,
            "max_tracker_items": MAX_OBJECTIVE_TRACKER_ITEMS,
        },
    }


def pin_objective(
    simulation_state: Dict[str, Any],
    objective_id: str,
    *,
    turn_index: int = 0,
    reason: str = "player_pinned",
) -> Dict[str, Any]:
    objective_id = str(objective_id or "")
    if not objective_id:
        return {"ok": False, "reason": "missing_objective_id"}

    projection = build_story_objective_projection(simulation_state, limit=MAX_QUEST_LOG_OBJECTIVES)
    active_ids = {
        str(row.get("objective_id") or "")
        for row in _safe_list(projection.get("active_objectives"))
        if isinstance(row, dict)
    }
    if objective_id not in active_ids:
        return {
            "ok": False,
            "reason": "objective_not_active",
            "objective_id": objective_id,
        }

    state = ensure_quest_log_state(simulation_state)
    pinned = list(state.get("pinned_objective_ids") or [])
    if objective_id in pinned:
        return {
            "ok": True,
            "reason": "already_pinned",
            "objective_id": objective_id,
            "pinned_objective_ids": pinned,
        }
    if len(pinned) >= MAX_PINNED_OBJECTIVES:
        return {
            "ok": False,
            "reason": "pinned_objective_limit_reached",
            "objective_id": objective_id,
            "max_pinned_objectives": MAX_PINNED_OBJECTIVES,
        }
    pinned.append(objective_id)
    state["pinned_objective_ids"] = pinned
    simulation_state["quest_log_state"] = state
    append_quest_log_history(
        simulation_state,
        objective_id=objective_id,
        action="pin",
        turn_index=turn_index,
        reason=reason,
    )
    return {
        "ok": True,
        "reason": "pinned",
        "objective_id": objective_id,
        "pinned_objective_ids": ensure_quest_log_state(simulation_state).get("pinned_objective_ids") or [],
    }


def unpin_objective(
    simulation_state: Dict[str, Any],
    objective_id: str,
    *,
    turn_index: int = 0,
    reason: str = "player_unpinned",
) -> Dict[str, Any]:
    objective_id = str(objective_id or "")
    if not objective_id:
        return {"ok": False, "reason": "missing_objective_id"}
    state = ensure_quest_log_state(simulation_state)
    pinned = list(state.get("pinned_objective_ids") or [])
    if objective_id not in pinned:
        return {
            "ok": True,
            "reason": "already_unpinned",
            "objective_id": objective_id,
            "pinned_objective_ids": pinned,
        }
    pinned = [item for item in pinned if item != objective_id]
    state["pinned_objective_ids"] = pinned
    simulation_state["quest_log_state"] = state
    append_quest_log_history(
        simulation_state,
        objective_id=objective_id,
        action="unpin",
        turn_index=turn_index,
        reason=reason,
    )
    return {
        "ok": True,
        "reason": "unpinned",
        "objective_id": objective_id,
        "pinned_objective_ids": ensure_quest_log_state(simulation_state).get("pinned_objective_ids") or [],
    }