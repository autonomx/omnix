from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal.journal import (
    build_campaign_journal,
    build_player_story_recap,
)
from app.rpg.story_arcs.milestones import (
    add_story_arc_milestone,
    build_story_objective_projection,
    complete_story_arc_milestone,
    get_story_arc_milestone,
    list_story_arc_milestones,
)
from app.rpg.story_events.application import apply_story_event


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_simulation_state(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session)
    session_setup_payload = _safe_dict(session_dict.get("setup_payload"))
    session_metadata = _safe_dict(session_setup_payload.get("metadata"))

    candidates = [
        session_dict.get("simulation_state"),
        session_metadata.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        _safe_dict(nested.get("session")).get("simulation_state"),
        result.get("simulation_state"),
        nested.get("simulation_state"),
    ]

    first_non_empty: Dict[str, Any] = {}
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate and not first_non_empty:
            first_non_empty = candidate
        if (
            isinstance(candidate.get("story_arc_milestone_state"), dict)
            or isinstance(candidate.get("story_arc_state"), dict)
            or isinstance(candidate.get("campaign_journal_state"), dict)
        ):
            return candidate

    return first_non_empty


def run_story_arc_milestones_m46_m48_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_arc_milestone_add":
        add_result = add_story_arc_milestone(
            simulation_state,
            arc_id=str(check.get("arc_id") or ""),
            milestone_id=str(check.get("milestone_id") or ""),
            title=str(check.get("title") or ""),
            summary=str(check.get("summary") or ""),
            objective_text=str(check.get("objective_text") or ""),
            journal_on_complete=str(check.get("journal_on_complete") or ""),
            quest_id=str(check.get("quest_id") or ""),
            priority=int(check.get("priority") or 50),
            turn_index=int(check.get("turn_index") or 1),
            tags=check.get("tags") or [],
        )
        expected_ok = check.get("expected_ok")
        ok = True
        if expected_ok is not None:
            ok = ok and add_result.get("ok") is bool(expected_ok)
        return {
            "check_type": check_type,
            "ok": ok,
            "add_result": add_result,
            "expected_ok": expected_ok,
        }

    if check_type == "story_arc_milestone_complete":
        complete_result = complete_story_arc_milestone(
            simulation_state,
            str(check.get("milestone_id") or ""),
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "manual_check"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and complete_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and complete_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "complete_result": complete_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "story_arc_milestone_status":
        milestone_id = str(check.get("milestone_id") or "")
        milestone = get_story_arc_milestone(simulation_state, milestone_id)
        expected_status = str(check.get("expected_status") or "")
        ok = bool(milestone)
        if expected_status:
            ok = ok and _safe_dict(milestone).get("status") == expected_status
        return {
            "check_type": check_type,
            "ok": ok,
            "milestone_id": milestone_id,
            "milestone": milestone,
            "expected_status": expected_status,
        }

    if check_type == "story_objective_projection":
        projection = build_story_objective_projection(
            simulation_state,
            limit=int(check.get("limit") or 25),
        )
        expected_objective_id = check.get("expected_objective_id")
        expected_active_count = check.get("expected_active_count")
        ok = projection.get("ok") is True
        if expected_objective_id:
            ok = ok and expected_objective_id in [
                row.get("objective_id") for row in projection.get("active_objectives") or []
            ]
        if expected_active_count is not None:
            ok = ok and len(projection.get("active_objectives") or []) == int(expected_active_count)
        return {
            "check_type": check_type,
            "ok": ok,
            "projection": projection,
            "expected_objective_id": expected_objective_id,
            "expected_active_count": expected_active_count,
        }

    if check_type == "story_event_apply_for_milestone":
        applied = apply_story_event(
            simulation_state,
            _safe_dict(check.get("event")),
            turn_index=int(check.get("turn_index") or 1),
        )
        expected_ok = check.get("expected_ok")
        ok = True
        if expected_ok is not None:
            ok = ok and applied.get("ok") is bool(expected_ok)
        return {
            "check_type": check_type,
            "ok": ok,
            "applied": applied,
            "expected_ok": expected_ok,
        }

    if check_type == "campaign_journal_objective_contains":
        journal = build_campaign_journal(simulation_state)
        expected_summary_contains = str(check.get("expected_summary_contains") or "")
        rows = [
            row
            for row in journal.get("entries") or []
            if row.get("kind") == "objective"
            and expected_summary_contains in str(row.get("summary") or "")
        ]
        return {
            "check_type": check_type,
            "ok": bool(rows),
            "journal": journal,
            "matched": rows,
            "expected_summary_contains": expected_summary_contains,
        }

    if check_type == "campaign_recap_objective":
        recap = build_player_story_recap(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            max_items=int(check.get("max_items") or 25),
        )
        expected_objective_id = check.get("expected_objective_id")
        objectives = _safe_dict(recap.get("objectives")).get("active_objectives") or []
        narrator_objectives = _safe_dict(recap.get("narrator_context")).get("active_objectives") or []
        ok = True
        if expected_objective_id:
            ok = ok and expected_objective_id in [row.get("objective_id") for row in objectives]
            ok = ok and expected_objective_id in [row.get("objective_id") for row in narrator_objectives]
        return {
            "check_type": check_type,
            "ok": ok,
            "recap": recap,
            "expected_objective_id": expected_objective_id,
        }

    if check_type == "story_arc_milestone_bounded":
        rows = list_story_arc_milestones(
            simulation_state,
            arc_id=str(check.get("arc_id") or ""),
            limit=100,
        )
        expected_max = int(check.get("expected_max") or 30)
        return {
            "check_type": check_type,
            "ok": len(rows) <= expected_max,
            "count": len(rows),
            "expected_max": expected_max,
            "rows": rows,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_arc_milestones_m46_m48_check_type:{check_type}",
    }


def run_story_arc_milestones_m46_m48_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in checks:
        check_type = str(_safe_dict(check).get("type") or "")
        try:
            check_result = run_story_arc_milestones_m46_m48_check(
                check=_safe_dict(check),
                result=result,
                session=session,
            )
        except Exception as exc:
            check_result = {
                "check_type": check_type,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if not isinstance(check_result, dict):
            check_result = {
                "check_type": check_type,
                "ok": False,
                "error": "check_returned_non_dict",
            }
        results.append(check_result)
    return results