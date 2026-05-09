from __future__ import annotations

from typing import Any, Dict, List, Set


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _quest_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(state)
    quest_progress = state.setdefault("quest_progress", {})
    if not isinstance(quest_progress, dict):
        quest_progress = {}
        state["quest_progress"] = quest_progress
    quests = quest_progress.setdefault("quests", {})
    if not isinstance(quests, dict):
        quests = {}
        quest_progress["quests"] = quests
    return quest_progress


def _objective_completed_from_log(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    return bool(row.get("matched")) and (
        bool(row.get("completed"))
        or _safe_str(row.get("status")) == "completed"
        or bool(row.get("objective_completed"))
    )


def _objective_progressed_from_log(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    return bool(row.get("matched")) and (
        bool(row.get("partial"))
        or bool(row.get("progressed"))
        or int(row.get("progress_count") or 0) > 0
    )


def _completed_objective_ids_from_log(state: Dict[str, Any]) -> Set[str]:
    completed: Set[str] = set()
    for row in _safe_list(_safe_dict(state).get("objective_progression_log")):
        row = _safe_dict(row)
        objective_id = _safe_str(row.get("objective_id") or row.get("id"))
        if objective_id and _objective_completed_from_log(row):
            completed.add(objective_id)
    return completed


def _progressed_objective_ids_from_log(state: Dict[str, Any]) -> Set[str]:
    progressed: Set[str] = set()
    for row in _safe_list(_safe_dict(state).get("objective_progression_log")):
        row = _safe_dict(row)
        objective_id = _safe_str(row.get("objective_id") or row.get("id"))
        if objective_id and _objective_progressed_from_log(row):
            progressed.add(objective_id)
    return progressed


def _find_objectives_by_id(state: Dict[str, Any], objective_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    objective_id = _safe_str(objective_id)
    if not objective_id:
        return out

    quest_progress_quests = _safe_dict(_safe_dict(state.get("quest_progress")).get("quests"))
    for quest in quest_progress_quests.values():
        for objective in _safe_list(_safe_dict(quest).get("objectives")):
            objective = _safe_dict(objective)
            if _safe_str(objective.get("objective_id") or objective.get("id")) == objective_id:
                out.append(objective)

    quest_log_quests = _safe_dict(_safe_dict(state.get("quest_log_state")).get("quests"))
    for quest in quest_log_quests.values():
        for objective in _safe_list(_safe_dict(quest).get("objectives")):
            objective = _safe_dict(objective)
            if _safe_str(objective.get("objective_id") or objective.get("id")) == objective_id:
                out.append(objective)

    arcs = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))
    for arc in arcs.values():
        for milestone in _safe_list(_safe_dict(arc).get("milestones")):
            milestone = _safe_dict(milestone)
            if _safe_str(
                milestone.get("objective_id")
                or milestone.get("milestone_id")
                or milestone.get("id")
            ) == objective_id:
                out.append(milestone)
    return out


def _mark_objective_completed(objective: Dict[str, Any]) -> bool:
    objective = _safe_dict(objective)
    before = bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed"
    objective["completed"] = True
    objective["status"] = "completed"
    return not before


def _mark_objective_progressed(objective: Dict[str, Any]) -> bool:
    objective = _safe_dict(objective)
    if bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed":
        return False
    before = int(objective.get("progress_count") or 0)
    objective["progress_count"] = max(before, 1)
    objective["status"] = _safe_str(objective.get("status") or "active")
    return before <= 0


def _sync_quest_completion(quest: Dict[str, Any]) -> bool:
    quest = _safe_dict(quest)
    objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
    if not objectives:
        return False
    all_done = all(
        bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed"
        for objective in objectives
    )
    before = bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"
    if all_done:
        quest["completed"] = True
        quest["status"] = "completed"
    elif _safe_str(quest.get("status")) != "completed":
        quest["completed"] = False
        quest["status"] = _safe_str(quest.get("status") or "active")
    return all_done and not before


def _sync_all_quest_completion(state: Dict[str, Any]) -> int:
    changed = 0
    for root in ("quest_progress", "quest_log_state"):
        quests = _safe_dict(_safe_dict(state.get(root)).get("quests"))
        for quest in quests.values():
            if _sync_quest_completion(_safe_dict(quest)):
                changed += 1
    return changed


def _promote_quest_log_to_quest_progress_if_needed(state: Dict[str, Any]) -> int:
    quest_progress = _quest_progress(state)
    quest_progress_quests = _safe_dict(quest_progress.get("quests"))
    quest_log_quests = _safe_dict(_safe_dict(state.get("quest_log_state")).get("quests"))
    changed = 0
    for quest_id, quest in quest_log_quests.items():
        if quest_id not in quest_progress_quests:
            quest_progress_quests[quest_id] = dict(_safe_dict(quest))
            changed += 1
    return changed


def reconcile_objective_progression_into_quests(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from app.rpg.campaign_state.authority_commit import commit_campaign_state

        result = commit_campaign_state(state, phase="turn")
        committed_state = _safe_dict(result.get("state")) or state
        summary = _safe_dict(result.get("summary"))
        reconciliation = _safe_dict(summary.get("quest_reconciliation_summary"))
        return {
            "changed": bool(
                reconciliation.get("completed_objective_updates")
                or reconciliation.get("partial_objective_updates")
                or reconciliation.get("quests_completed")
                or reconciliation.get("quest_promotions")
            ),
            "state": committed_state,
            "completed_objective_ids": [
                _safe_str(row.get("objective_id"))
                for row in _safe_list(summary.get("objective_evidence"))
                if _safe_dict(row).get("completed")
            ],
            "progressed_objective_ids": [
                _safe_str(row.get("objective_id"))
                for row in _safe_list(summary.get("objective_evidence"))
                if _safe_dict(row).get("partial")
            ],
            "completed_objective_updates": int(reconciliation.get("completed_objective_updates") or 0),
            "progressed_objective_updates": int(reconciliation.get("partial_objective_updates") or 0),
            "quest_promotions": int(reconciliation.get("quest_promotions") or 0),
            "quests_completed": int(reconciliation.get("quests_completed") or 0),
            "authority_commit_summary": summary,
        }
    except RecursionError:
        pass
    except Exception:
        pass

    """Apply objective progression diagnostics to canonical quest state."""
    state = _safe_dict(state)
    changed = False
    completed_ids = _completed_objective_ids_from_log(state)
    progressed_ids = _progressed_objective_ids_from_log(state)

    quest_promotions = _promote_quest_log_to_quest_progress_if_needed(state)
    if quest_promotions:
        changed = True

    completed_updates = 0
    progressed_updates = 0
    for objective_id in sorted(completed_ids):
        for objective in _find_objectives_by_id(state, objective_id):
            if _mark_objective_completed(objective):
                changed = True
                completed_updates += 1

    for objective_id in sorted(progressed_ids - completed_ids):
        for objective in _find_objectives_by_id(state, objective_id):
            if _mark_objective_progressed(objective):
                changed = True
                progressed_updates += 1

    quests_completed = _sync_all_quest_completion(state)
    if quests_completed:
        changed = True

    reconciliation_log = state.setdefault("quest_reconciliation_log", [])
    if isinstance(reconciliation_log, list):
        reconciliation_log.append(
            {
                "changed": changed,
                "completed_objective_ids": sorted(completed_ids),
                "progressed_objective_ids": sorted(progressed_ids),
                "completed_objective_updates": completed_updates,
                "progressed_objective_updates": progressed_updates,
                "quest_promotions": quest_promotions,
                "quests_completed": quests_completed,
            }
        )
        del reconciliation_log[:-100]

    return {
        "changed": changed,
        "state": state,
        "completed_objective_ids": sorted(completed_ids),
        "progressed_objective_ids": sorted(progressed_ids),
        "completed_objective_updates": completed_updates,
        "progressed_objective_updates": progressed_updates,
        "quest_promotions": quest_promotions,
        "quests_completed": quests_completed,
    }