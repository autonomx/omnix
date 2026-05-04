from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal.journal import build_player_story_recap
from app.rpg.quest_log.runtime import (
    build_objective_tracker_payload,
    build_quest_log_payload,
    pin_objective,
    unpin_objective,
)


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
            isinstance(candidate.get("quest_log_state"), dict)
            or isinstance(candidate.get("story_arc_milestone_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_quest_log_m49_m51_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "quest_log_payload":
        payload = build_quest_log_payload(simulation_state, limit=int(check.get("limit") or 50))
        expected_active_objective_id = check.get("expected_active_objective_id")
        expected_completed_objective_id = check.get("expected_completed_objective_id")
        expected_active_count = check.get("expected_active_count")
        ok = payload.get("ok") is True
        if expected_active_objective_id:
            ok = ok and expected_active_objective_id in [
                row.get("objective_id") for row in payload.get("active_objectives") or []
            ]
        if expected_completed_objective_id:
            ok = ok and expected_completed_objective_id in [
                row.get("objective_id") for row in payload.get("completed_objectives") or []
            ]
        if expected_active_count is not None:
            ok = ok and len(payload.get("active_objectives") or []) == int(expected_active_count)
        return {
            "check_type": check_type,
            "ok": ok,
            "payload": payload,
            "expected_active_objective_id": expected_active_objective_id,
            "expected_completed_objective_id": expected_completed_objective_id,
            "expected_active_count": expected_active_count,
        }

    if check_type == "objective_tracker_payload":
        payload = build_objective_tracker_payload(simulation_state, limit=int(check.get("limit") or 8))
        expected_objective_id = check.get("expected_objective_id")
        expected_first_objective_id = check.get("expected_first_objective_id")
        ok = payload.get("ok") is True
        objectives = payload.get("objectives") or []
        if expected_objective_id:
            ok = ok and expected_objective_id in [row.get("objective_id") for row in objectives]
        if expected_first_objective_id:
            ok = ok and bool(objectives) and objectives[0].get("objective_id") == expected_first_objective_id
        return {
            "check_type": check_type,
            "ok": ok,
            "payload": payload,
            "expected_objective_id": expected_objective_id,
            "expected_first_objective_id": expected_first_objective_id,
        }

    if check_type == "quest_log_pin":
        pin_result = pin_objective(
            simulation_state,
            str(check.get("objective_id") or ""),
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "manual_pin"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and pin_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and pin_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "pin_result": pin_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "quest_log_unpin":
        unpin_result = unpin_objective(
            simulation_state,
            str(check.get("objective_id") or ""),
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "manual_unpin"),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and unpin_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and unpin_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "unpin_result": unpin_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "campaign_recap_objective_tracker":
        recap = build_player_story_recap(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            max_items=int(check.get("max_items") or 25),
        )
        expected_objective_id = check.get("expected_objective_id")
        objectives = _safe_dict(recap.get("objective_tracker")).get("objectives") or []
        narrator_tracker = _safe_dict(recap.get("narrator_context")).get("objective_tracker") or []
        ok = True
        if expected_objective_id:
            ok = ok and expected_objective_id in [row.get("objective_id") for row in objectives]
            ok = ok and expected_objective_id in [row.get("objective_id") for row in narrator_tracker]
        return {
            "check_type": check_type,
            "ok": ok,
            "recap": recap,
            "expected_objective_id": expected_objective_id,
        }

    if check_type == "quest_log_debug_bounded":
        quest_log = build_quest_log_payload(simulation_state, limit=int(check.get("limit") or 50))
        tracker = build_objective_tracker_payload(simulation_state, limit=int(check.get("tracker_limit") or 8))
        return {
            "check_type": check_type,
            "ok": (
                len(quest_log.get("active_objectives") or []) <= int(check.get("limit") or 50)
                and len(tracker.get("objectives") or []) <= int(check.get("tracker_limit") or 8)
            ),
            "quest_log": quest_log,
            "tracker": tracker,
            "limit": check.get("limit") or 50,
            "tracker_limit": check.get("tracker_limit") or 8,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_quest_log_m49_m51_check_type:{check_type}",
    }


def run_quest_log_m49_m51_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in checks:
        check_type = str(_safe_dict(check).get("type") or "")
        try:
            check_result = run_quest_log_m49_m51_check(
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
        results.append(check_result)
    return results