from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def sync_witness_quest_from_milestones(state: Dict[str, Any]) -> None:
    """Keep quest_progress aligned with deterministic witness milestones."""
    state = _safe_dict(state)
    arcs = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))
    witness_arc = _safe_dict(arcs.get("arc:witness_search") or arcs.get("witness_search"))
    milestones = _safe_list(witness_arc.get("milestones"))
    completed_ids = {
        _safe_str(row.get("milestone_id"))
        for row in milestones
        if _safe_str(_safe_dict(row).get("status")) == "completed"
    }
    completed_titles = {
        _safe_str(row.get("title")).lower()
        for row in milestones
        if _safe_str(_safe_dict(row).get("status")) == "completed"
    }
    if not completed_ids and not completed_titles:
        fired_hooks = set(
            _safe_dict(_safe_dict(state.get("autoplay_story_hook_state")).get("fired_hooks")).keys()
        )
        hook_to_milestone = {
            "hook:witness:find_witness": "milestone:find_witness",
            "hook:witness:report_to_bran": "milestone:report_findings_to_bran",
            "hook:witness:pursue_bandit_trail": "milestone:pursue_bandit_trail",
        }
        for hook_id, milestone_id in hook_to_milestone.items():
            if hook_id in fired_hooks:
                completed_ids.add(milestone_id)
    if not completed_ids and not completed_titles:
        # Still allow action-derived sync below if the run has recorded witness facts.
        pass

    witness_facts = _safe_dict(state.get("witness_search_facts"))
    report_action_seen = bool(witness_facts.get("reported_to_bran"))

    quest_progress = state.setdefault("quest_progress", {})
    if not isinstance(quest_progress, dict):
        quest_progress = {}
        state["quest_progress"] = quest_progress
    quests = quest_progress.setdefault("quests", {})
    if not isinstance(quests, dict):
        quests = {}
        quest_progress["quests"] = quests

    quest = quests.setdefault(
        "quest:witness_search",
        {
            "quest_id": "quest:witness_search",
            "title": "Witness Search",
            "status": "active",
            "objectives": [
                {
                    "objective_id": "objective:find_witness",
                    "summary": "Find the witness.",
                    "status": "active",
                    "completed": False,
                },
                {
                    "objective_id": "objective:report_findings_to_bran",
                    "summary": "Report findings to Bran.",
                    "status": "active",
                    "completed": False,
                },
            ],
        },
    )
    objectives = _safe_list(_safe_dict(quest).get("objectives"))
    if not objectives:
        objectives = [
            {
                "objective_id": "objective:find_witness",
                "summary": "Find the witness.",
                "status": "active",
                "completed": False,
            },
            {
                "objective_id": "objective:report_findings_to_bran",
                "summary": "Report findings to Bran.",
                "status": "active",
                "completed": False,
            },
        ]
        quest["objectives"] = objectives

    def complete_matching_objective(*, wanted_id: str, title_terms: List[str]) -> None:
        for obj in objectives:
            obj = _safe_dict(obj)
            blob = " ".join(
                [
                    _safe_str(obj.get("objective_id")),
                    _safe_str(obj.get("summary")),
                    _safe_str(obj.get("objective_text")),
                    _safe_str(obj.get("title")),
                ]
            ).lower()
            if wanted_id in blob or any(term in blob for term in title_terms):
                obj["completed"] = True
                obj["status"] = "completed"

    if (
        "milestone:find_witness" in completed_ids
        or "find the witness" in completed_titles
        or "find witness" in completed_titles
    ):
        complete_matching_objective(
            wanted_id="find_witness",
            title_terms=["find the witness", "find witness"],
        )

    if (
        "milestone:report_findings_to_bran" in completed_ids
        or "report findings to bran" in completed_titles
        or "report to bran" in completed_titles
        or report_action_seen
        or "milestone:pursue_bandit_trail" in completed_ids
        or "pursue bandit trail" in completed_titles
    ):
        complete_matching_objective(
            wanted_id="report_findings_to_bran",
            title_terms=["report findings", "report to bran"],
        )

    completed_count = sum(1 for obj in objectives if _safe_dict(obj).get("completed") is True)
    quest["completed_objective_count"] = completed_count
    quest["objective_count"] = len(objectives)
    if objectives and completed_count >= len(objectives):
        quest["status"] = "completed"
        quest["completed"] = True

    # Activate next quest hook once the witness trail points to the road.
    if (
        "milestone:report_findings_to_bran" in completed_ids
        or "report findings to bran" in completed_titles
        or "report to bran" in completed_titles
        or
        "milestone:pursue_bandit_trail" in completed_ids
        or "pursue bandit trail" in completed_titles
        or "prepare for bandit road" in completed_titles
    ):
        quests.setdefault(
            "quest:bandit_road",
            {
                "quest_id": "quest:bandit_road",
                "title": "Bandit Road",
                "status": "active",
                "objectives": [
                    {
                        "objective_id": "objective:prepare_for_bandit_road",
                        "summary": "Prepare for the bandit road.",
                        "status": "active",
                        "completed": False,
                    },
                    {
                        "objective_id": "objective:follow_bandit_road",
                        "summary": "Follow the bandit road trail.",
                        "status": "active",
                        "completed": False,
                    },
                ],
            },
        )
