from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def state_digest(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Small deterministic digest for before/after comparisons."""
    state = _safe_dict(simulation_state)
    selected = {
        "story_arc_state": state.get("story_arc_state"),
        "story_arc_milestone_state": state.get("story_arc_milestone_state"),
        "campaign_journal_state": state.get("campaign_journal_state"),
        "quest_log_state": state.get("quest_log_state"),
        "story_event_queue_state": state.get("story_event_queue_state"),
        "npc_evolution_state": state.get("npc_evolution_state"),
        "social_state": state.get("social_state"),
        "combat_state": state.get("combat_state"),
        "scene": state.get("scene"),
        "location": state.get("location"),
        "runtime": state.get("runtime"),
    }
    encoded = _stable_json(selected)
    return {
        "hash": hashlib.sha1(encoded.encode("utf-8")).hexdigest(),
        "size_bytes": len(encoded.encode("utf-8")),
        "counts": {
            "arcs": len(_safe_dict(_safe_dict(state.get("story_arc_state")).get("arcs"))),
            "milestone_arcs": len(_safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))),
            "journal_entries": len(_safe_list(_safe_dict(state.get("campaign_journal_state")).get("entries"))),
            "queued_events": len(_safe_list(_safe_dict(state.get("story_event_queue_state")).get("queue"))),
        },
    }


def _milestone_rows(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    milestone_state = _safe_dict(state.get("story_arc_milestone_state"))
    for bucket in _safe_dict(milestone_state.get("arcs")).values():
        for row in _safe_list(_safe_dict(bucket).get("milestones")):
            if isinstance(row, dict) and row.get("milestone_id"):
                out[str(row["milestone_id"])] = row
    return out


def _arc_rows(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(arc_id): row
        for arc_id, row in _safe_dict(_safe_dict(state.get("story_arc_state")).get("arcs")).items()
        if isinstance(row, dict)
    }


def _journal_entries(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in _safe_list(_safe_dict(state.get("campaign_journal_state")).get("entries"))
        if isinstance(row, dict)
    ]


def classify_progress_delta(
    *,
    before_state: Dict[str, Any],
    after_state: Dict[str, Any],
) -> Dict[str, Any]:
    before_digest = state_digest(before_state)
    after_digest = state_digest(after_state)

    before_milestones = _milestone_rows(before_state)
    after_milestones = _milestone_rows(after_state)
    before_arcs = _arc_rows(before_state)
    after_arcs = _arc_rows(after_state)
    before_journal = _journal_entries(before_state)
    after_journal = _journal_entries(after_state)

    added_milestones = [
        milestone_id
        for milestone_id in after_milestones
        if milestone_id not in before_milestones
    ]
    completed_milestones = [
        milestone_id
        for milestone_id, row in after_milestones.items()
        if row.get("status") == "completed"
        and _safe_dict(before_milestones.get(milestone_id)).get("status") != "completed"
    ]
    arc_stage_changes = [
        {
            "arc_id": arc_id,
            "before": _safe_dict(before_arcs.get(arc_id)).get("stage"),
            "after": row.get("stage"),
        }
        for arc_id, row in after_arcs.items()
        if _safe_dict(before_arcs.get(arc_id)).get("stage") != row.get("stage")
    ]
    new_journal_entries = max(0, len(after_journal) - len(before_journal))

    categories: List[str] = []
    if added_milestones:
        categories.append("milestone_added")
    if completed_milestones:
        categories.append("milestone_completed")
    if arc_stage_changes:
        categories.append("arc_stage_changed")
    if new_journal_entries:
        categories.append("journal_entry_added")
    if before_digest["hash"] != after_digest["hash"] and not categories:
        categories.append("state_changed")

    return {
        "changed": before_digest["hash"] != after_digest["hash"],
        "categories": categories,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "added_milestones": added_milestones,
        "completed_milestones": completed_milestones,
        "arc_stage_changes": arc_stage_changes,
        "new_journal_entries": new_journal_entries,
    }


def no_progress_streak(transcript: List[Dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(transcript):
        progress = _safe_dict(row.get("progress_delta"))
        if progress.get("changed") or progress.get("categories"):
            break
        streak += 1
    return streak