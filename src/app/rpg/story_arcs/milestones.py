from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

MAX_ARC_MILESTONES_PER_ARC = 30
MAX_ARC_MILESTONE_HISTORY = 200


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


def _stable_milestone_id(*, arc_id: str, title: str, index: int = 0) -> str:
    payload = json.dumps(
        {"arc_id": arc_id, "title": title, "index": int(index or 0)},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"milestone:{digest}"


def normalize_story_arc_milestone(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    status = _safe_str(value.get("status")) or "active"
    if status not in {"active", "completed", "failed", "hidden"}:
        status = "active"
    return {
        "milestone_id": _safe_str(value.get("milestone_id")),
        "arc_id": _safe_str(value.get("arc_id")),
        "title": _safe_str(value.get("title")),
        "summary": _safe_str(value.get("summary")),
        "status": status,
        "created_turn": _safe_int(value.get("created_turn"), 0),
        "completed_turn": _safe_int(value.get("completed_turn"), 0),
        "objective_text": _safe_str(value.get("objective_text")),
        "journal_on_complete": _safe_str(value.get("journal_on_complete")),
        "quest_id": _safe_str(value.get("quest_id")),
        "priority": max(0, min(100, _safe_int(value.get("priority"), 50))),
        "tags": [str(item) for item in _safe_list(value.get("tags")) if str(item)][:20],
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_arc_milestone_history_item(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "milestone_id": _safe_str(value.get("milestone_id")),
        "arc_id": _safe_str(value.get("arc_id")),
        "action": _safe_str(value.get("action")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "reason": _safe_str(value.get("reason")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_arc_milestone_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    arcs: Dict[str, Dict[str, Any]] = {}
    for arc_id, rows in _safe_dict(value.get("arcs")).items():
        arc_id = str(arc_id or "")
        if not arc_id:
            continue
        # Current canonical shape:
        #   arcs[arc_id] = {"milestones": [...]}
        #
        # Earlier/looser callers may still pass:
        #   arcs[arc_id] = [...]
        #
        # Support both so normalization is save/load-safe and does not erase
        # milestones every time ensure_story_arc_milestone_state() runs.
        if isinstance(rows, dict):
            raw_milestones = rows.get("milestones")
        else:
            raw_milestones = rows
        milestones = [
            normalize_story_arc_milestone(row)
            for row in _safe_list(raw_milestones)
            if isinstance(row, dict)
        ]
        milestones = [
            row
            for row in milestones
            if row.get("milestone_id") and row.get("arc_id")
        ][:MAX_ARC_MILESTONES_PER_ARC]
        milestones.sort(
            key=lambda row: (
                row.get("status") != "active",
                -int(row.get("priority") or 0),
                int(row.get("created_turn") or 0),
                str(row.get("milestone_id") or ""),
            )
        )
        arcs[arc_id] = {"milestones": milestones}

    history = [
        normalize_story_arc_milestone_history_item(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_ARC_MILESTONE_HISTORY:]

    return {
        "version": 1,
        "arcs": arcs,
        "history": history,
        "max_milestones_per_arc": MAX_ARC_MILESTONES_PER_ARC,
        "max_history": MAX_ARC_MILESTONE_HISTORY,
    }


def ensure_story_arc_milestone_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_arc_milestone_state(simulation_state.get("story_arc_milestone_state"))
    simulation_state["story_arc_milestone_state"] = state
    return state


def _append_history(
    simulation_state: Dict[str, Any],
    *,
    milestone_id: str,
    arc_id: str,
    action: str,
    turn_index: int = 0,
    reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> None:
    state = ensure_story_arc_milestone_state(simulation_state)
    history = list(state.get("history") or [])
    history.append(
        normalize_story_arc_milestone_history_item(
            {
                "milestone_id": milestone_id,
                "arc_id": arc_id,
                "action": action,
                "turn_index": turn_index,
                "reason": reason,
                "metadata": metadata or {},
            }
        )
    )
    state["history"] = history[-MAX_ARC_MILESTONE_HISTORY:]
    simulation_state["story_arc_milestone_state"] = normalize_story_arc_milestone_state(state)


def add_story_arc_milestone(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str,
    title: str,
    summary: str = "",
    milestone_id: str = "",
    objective_text: str = "",
    journal_on_complete: str = "",
    quest_id: str = "",
    priority: int = 50,
    turn_index: int = 0,
    tags: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    arc_id = str(arc_id or "")
    title = str(title or "")
    if not arc_id:
        return {"ok": False, "reason": "missing_arc_id"}
    if not title:
        return {"ok": False, "reason": "missing_title"}

    story_arc_state = _safe_dict(simulation_state.get("story_arc_state"))
    arcs = _safe_dict(story_arc_state.get("arcs"))
    if arc_id not in arcs:
        return {"ok": False, "reason": "story_arc_missing", "arc_id": arc_id}

    state = ensure_story_arc_milestone_state(simulation_state)
    arc_bucket = state.setdefault("arcs", {}).setdefault(arc_id, {"milestones": []})
    milestones = list(arc_bucket.get("milestones") or [])
    resolved_id = milestone_id or _stable_milestone_id(arc_id=arc_id, title=title, index=len(milestones))

    for row in milestones:
        if row.get("milestone_id") == resolved_id:
            return {
                "ok": True,
                "reason": "already_exists",
                "milestone": row,
            }

    if len(milestones) >= MAX_ARC_MILESTONES_PER_ARC:
        return {
            "ok": False,
            "reason": "milestone_limit_reached",
            "arc_id": arc_id,
            "max_milestones_per_arc": MAX_ARC_MILESTONES_PER_ARC,
        }

    milestone = normalize_story_arc_milestone(
        {
            "milestone_id": resolved_id,
            "arc_id": arc_id,
            "title": title,
            "summary": summary,
            "status": "active",
            "created_turn": turn_index,
            "objective_text": objective_text or title,
            "journal_on_complete": journal_on_complete,
            "quest_id": quest_id,
            "priority": priority,
            "tags": tags or [],
            "metadata": metadata or {},
        }
    )
    milestones.append(milestone)
    arc_bucket["milestones"] = milestones
    state["arcs"][arc_id] = arc_bucket
    simulation_state["story_arc_milestone_state"] = normalize_story_arc_milestone_state(state)
    _append_history(
        simulation_state,
        milestone_id=resolved_id,
        arc_id=arc_id,
        action="add",
        turn_index=turn_index,
        reason="added",
    )
    return {
        "ok": True,
        "reason": "added",
        "milestone": get_story_arc_milestone(simulation_state, resolved_id),
    }


def get_story_arc_milestone(
    simulation_state: Dict[str, Any],
    milestone_id: str,
) -> Dict[str, Any] | None:
    state = ensure_story_arc_milestone_state(simulation_state)
    for bucket in _safe_dict(state.get("arcs")).values():
        for row in _safe_list(_safe_dict(bucket).get("milestones")):
            if isinstance(row, dict) and row.get("milestone_id") == milestone_id:
                return row
    return None


def complete_story_arc_milestone(
    simulation_state: Dict[str, Any],
    milestone_id: str,
    *,
    turn_index: int = 0,
    reason: str = "completed",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    milestone_id = str(milestone_id or "")
    if not milestone_id:
        return {"ok": False, "reason": "missing_milestone_id"}

    state = ensure_story_arc_milestone_state(simulation_state)
    for arc_id, bucket in _safe_dict(state.get("arcs")).items():
        milestones = []
        found = None
        for row in _safe_list(_safe_dict(bucket).get("milestones")):
            if not isinstance(row, dict):
                continue
            row = dict(row)
            if row.get("milestone_id") == milestone_id:
                found = row
                if row.get("status") == "completed":
                    return {
                        "ok": True,
                        "reason": "already_completed",
                        "milestone_id": milestone_id,
                        "milestone": row,
                    }
                row["status"] = "completed"
                row["completed_turn"] = int(turn_index or 0)
                row["metadata"] = {**dict(row.get("metadata") or {}), **dict(metadata or {})}
                found = normalize_story_arc_milestone(row)
                milestones.append(found)
            else:
                milestones.append(row)
        if found:
            state["arcs"][arc_id] = {"milestones": milestones}
            simulation_state["story_arc_milestone_state"] = normalize_story_arc_milestone_state(state)
            _append_history(
                simulation_state,
                milestone_id=milestone_id,
                arc_id=str(arc_id),
                action="complete",
                turn_index=turn_index,
                reason=reason,
                metadata=metadata,
            )
            return {
                "ok": True,
                "reason": "completed",
                "milestone_id": milestone_id,
                "milestone": get_story_arc_milestone(simulation_state, milestone_id),
            }

    return {"ok": False, "reason": "milestone_missing", "milestone_id": milestone_id}


def list_story_arc_milestones(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str = "",
    status: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    state = ensure_story_arc_milestone_state(simulation_state)
    rows: List[Dict[str, Any]] = []
    for bucket_arc_id, bucket in _safe_dict(state.get("arcs")).items():
        if arc_id and bucket_arc_id != arc_id:
            continue
        for row in _safe_list(_safe_dict(bucket).get("milestones")):
            if not isinstance(row, dict):
                continue
            if status and row.get("status") != status:
                continue
            rows.append(dict(row))
    rows.sort(
        key=lambda row: (
            row.get("status") != "active",
            -int(row.get("priority") or 0),
            int(row.get("created_turn") or 0),
            str(row.get("milestone_id") or ""),
        )
    )
    return rows[: max(0, min(100, int(limit or 50)))]


def build_story_objective_projection(
    simulation_state: Dict[str, Any],
    *,
    limit: int = 25,
) -> Dict[str, Any]:
    limit = max(0, min(50, int(limit or 25)))
    active = list_story_arc_milestones(simulation_state, status="active", limit=limit)
    completed = list_story_arc_milestones(simulation_state, status="completed", limit=limit)
    objectives = [
        {
            "objective_id": row.get("milestone_id"),
            "milestone_id": row.get("milestone_id"),
            "arc_id": row.get("arc_id"),
            "quest_id": row.get("quest_id"),
            "title": row.get("title"),
            "objective_text": row.get("objective_text") or row.get("title"),
            "status": row.get("status"),
            "priority": row.get("priority"),
        }
        for row in active[:limit]
    ]
    return {
        "ok": True,
        "format_version": "story_objective_projection_v1",
        "active_objectives": objectives,
        "completed_milestones": completed[:limit],
        "bounded": {
            "limit": limit,
            "max_milestones_per_arc": MAX_ARC_MILESTONES_PER_ARC,
        },
    }