from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


QUEST_PROGRESS_VERSION = "quest_progress_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def normalize_quest_status(value: Any) -> str:
    status = _safe_str(value).strip().lower()
    if status in {"done", "complete", "completed", "success", "resolved"}:
        return "completed"
    if status in {"fail", "failed"}:
        return "failed"
    if status in {"active", "started", "in_progress", "open", "ongoing"}:
        return "active"
    if status in {"blocked", "paused"}:
        return status
    return status or "unknown"


def starter_quest_state_for_seed(scenario_seed: str) -> Dict[str, Any]:
    """Deterministic starter quest state for known autoplay/base seeds.

    This is seed data, not LLM output. It does not grant rewards or mutate
    unrelated simulation state.
    """
    seed = _safe_str(scenario_seed).strip().lower()
    if seed != "tavern_story_seed":
        return {}

    return {
        "format_version": QUEST_PROGRESS_VERSION,
        "quests": {
            "quest:witness_search": {
                "quest_id": "quest:witness_search",
                "title": "Witness Search",
                "status": "active",
                "source": "scenario_seed",
                "giver": "Bran",
                "location": "Rusty Flagon Tavern",
                "summary": "Trouble on the road has reached the tavern, and Bran needs the player to find who saw what happened.",
                "objectives": [
                    {
                        "objective_id": "objective:find_witness",
                        "summary": "Find the witness",
                        "status": "active",
                        "completed": False,
                    },
                    {
                        "objective_id": "objective:report_to_bran",
                        "summary": "Report findings to Bran",
                        "status": "active",
                        "completed": False,
                    },
                ],
                "created_turn": 1,
                "updated_turn": 1,
            }
        },
        "timeline": [
            {
                "turn_index": 1,
                "quest_id": "quest:witness_search",
                "status": "active",
                "summary": "Witness Search started.",
                "source": "scenario_seed",
            }
        ],
    }


def ensure_quest_runtime_state(
    *,
    runtime_state: Dict[str, Any],
    scenario_seed: str = "",
) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    quest_state = runtime_state.setdefault(
        "quest_progress",
        {
            "format_version": QUEST_PROGRESS_VERSION,
            "quests": {},
            "timeline": [],
        },
    )
    quest_state.setdefault("format_version", QUEST_PROGRESS_VERSION)
    quest_state.setdefault("quests", {})
    quest_state.setdefault("timeline", [])

    seeded = starter_quest_state_for_seed(scenario_seed)
    seeded_quests = _safe_dict(seeded.get("quests"))
    if seeded_quests:
        for quest_id, quest_any in seeded_quests.items():
            if quest_id not in _safe_dict(quest_state.get("quests")):
                quest_state["quests"][quest_id] = deepcopy(_safe_dict(quest_any))
        existing_markers = {
            (
                _safe_str(item.get("turn_index")),
                _safe_str(item.get("quest_id")),
                _safe_str(item.get("summary")),
            )
            for item in _safe_list(quest_state.get("timeline"))
            if isinstance(item, dict)
        }
        for item in _safe_list(seeded.get("timeline")):
            item = _safe_dict(item)
            marker = (
                _safe_str(item.get("turn_index")),
                _safe_str(item.get("quest_id")),
                _safe_str(item.get("summary")),
            )
            if marker not in existing_markers:
                quest_state["timeline"].append(deepcopy(item))
                existing_markers.add(marker)

    runtime_state["quest_progress"] = quest_state
    return runtime_state


def quest_rows_from_story_arc_view(story_arc_view: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project story_arc_view into quest-like rows for report UX."""
    story_arc_view = _safe_dict(story_arc_view)
    rows: List[Dict[str, Any]] = []

    for arc in _safe_list(story_arc_view.get("arcs")):
        arc = _safe_dict(arc)
        arc_id = _safe_str(arc.get("arc_id") or arc.get("id") or arc.get("title"))
        if not arc_id:
            continue
        title = _safe_str(arc.get("title") or arc.get("name") or arc_id)
        status = normalize_quest_status(arc.get("status") or "active")
        objectives: List[Dict[str, Any]] = []

        for milestone in _safe_list(arc.get("milestones")):
            milestone = _safe_dict(milestone)
            summary = _safe_str(
                milestone.get("title")
                or milestone.get("objective_text")
                or milestone.get("summary")
                or milestone.get("name")
            )
            if not summary:
                continue
            milestone_status = normalize_quest_status(milestone.get("status") or "active")
            objectives.append(
                {
                    "objective_id": _safe_str(milestone.get("milestone_id") or milestone.get("id") or summary),
                    "summary": summary,
                    "status": milestone_status,
                    "completed": milestone_status == "completed",
                    "source": "story_arc_view",
                }
            )

        # Some arc models expose unresolved objectives directly.
        for objective in _safe_list(arc.get("objectives")):
            objective = _safe_dict(objective)
            summary = _safe_str(objective.get("summary") or objective.get("title") or objective.get("name"))
            if not summary:
                continue
            objective_status = normalize_quest_status(objective.get("status") or "active")
            objectives.append(
                {
                    "objective_id": _safe_str(objective.get("objective_id") or objective.get("id") or summary),
                    "summary": summary,
                    "status": objective_status,
                    "completed": bool(objective.get("completed")) or objective_status == "completed",
                    "source": "story_arc_view",
                }
            )

        rows.append(
            {
                "quest_id": _safe_str(arc.get("quest_id") or f"quest:{arc_id}"),
                "title": title,
                "status": status,
                "summary": _safe_str(arc.get("summary") or arc.get("stage") or arc.get("description")),
                "objectives": _dedupe_objectives(objectives),
                "source": "story_arc_view",
            }
        )

    return rows


def _dedupe_objectives(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for objective in objectives:
        objective = _safe_dict(objective)
        marker = _safe_str(objective.get("objective_id") or objective.get("summary")).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        out.append(objective)
    return out


def summarize_runtime_quests(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    quest_state = _safe_dict(_safe_dict(runtime_state).get("quest_progress"))
    quests = []
    for quest_id, quest_any in sorted(_safe_dict(quest_state.get("quests")).items()):
        quest = _safe_dict(quest_any)
        quest.setdefault("quest_id", str(quest_id))
        quests.append(quest)
    return {
        "format_version": QUEST_PROGRESS_VERSION,
        "quest_count": len(quests),
        "quests": quests,
        "timeline": _safe_list(quest_state.get("timeline"))[-50:],
    }