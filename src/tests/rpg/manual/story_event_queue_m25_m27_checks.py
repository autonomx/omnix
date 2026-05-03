from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_event_queue.queue import (
    enqueue_story_event,
    enqueue_story_event_definition,
    process_story_event_queue,
)
from app.rpg.story_events.state import get_applied_story_event


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_simulation_state(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session) if session else {}
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
        if isinstance(candidate.get("story_event_queue_state"), dict):
            return candidate
        if isinstance(candidate.get("story_arc_state"), dict):
            return candidate
        if isinstance(candidate.get("story_event_registry"), dict):
            return candidate
        if isinstance(candidate.get("story_pack_state"), dict):
            return candidate
    return first_non_empty


def run_story_event_queue_m25_m27_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_event_queue_enqueue":
        if check.get("definition_event_id"):
            enqueue_result = enqueue_story_event_definition(
                simulation_state,
                str(check.get("definition_event_id") or ""),
                source=str(check.get("source") or "manual_check"),
                enqueued_turn=int(check.get("enqueued_turn") or 1),
                due_turn=check.get("due_turn"),
                delay_turns=int(check.get("delay_turns") or 0),
                priority=int(check.get("priority") or 50),
                reason=str(check.get("reason") or ""),
            )
        else:
            enqueue_result = enqueue_story_event(
                simulation_state,
                _safe_dict(check.get("event")),
                source=str(check.get("source") or "manual_check"),
                enqueued_turn=int(check.get("enqueued_turn") or 1),
                due_turn=check.get("due_turn"),
                delay_turns=int(check.get("delay_turns") or 0),
                priority=int(check.get("priority") or 50),
                reason=str(check.get("reason") or ""),
            )
        expected_ok = check.get("expected_ok")
        expected_queued = check.get("expected_queued")
        ok = True
        if expected_ok is not None:
            ok = ok and enqueue_result.get("ok") is bool(expected_ok)
        if expected_queued is not None:
            ok = ok and enqueue_result.get("queued") is bool(expected_queued)
        return {
            "check_type": check_type,
            "ok": ok,
            "enqueue_result": enqueue_result,
            "expected_ok": expected_ok,
            "expected_queued": expected_queued,
        }

    if check_type == "story_event_queue_process":
        process_result = process_story_event_queue(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            max_applications=int(check.get("max_applications") or 3),
        )
        expected_applied_count = check.get("expected_applied_count")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_applied_count is not None:
            ok = ok and int(process_result.get("applied_count") or 0) == int(expected_applied_count)
        if expected_reason:
            ok = ok and process_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "process_result": process_result,
            "expected_applied_count": expected_applied_count,
            "expected_reason": expected_reason,
        }

    if check_type == "story_event_queue_pending":
        state = _safe_dict(simulation_state.get("story_event_queue_state"))
        pending = state.get("pending") or []
        expected_count = check.get("expected_count")
        expected_event_id = check.get("expected_event_id")
        ok = True
        if expected_count is not None:
            ok = ok and len(pending) == int(expected_count)
        if expected_event_id:
            ok = ok and expected_event_id in [row.get("event_id") for row in pending if isinstance(row, dict)]
        return {
            "check_type": check_type,
            "ok": ok,
            "pending": pending,
            "expected_count": expected_count,
            "expected_event_id": expected_event_id,
        }

    if check_type == "story_event_queue_history":
        state = _safe_dict(simulation_state.get("story_event_queue_state"))
        history = state.get("history") or []
        expected_event_id = check.get("expected_event_id")
        expected_status = check.get("expected_status")
        rows = [
            row
            for row in history
            if isinstance(row, dict)
            and (not expected_event_id or row.get("event_id") == expected_event_id)
            and (not expected_status or row.get("status") == expected_status)
        ]
        return {
            "check_type": check_type,
            "ok": bool(rows),
            "expected_event_id": expected_event_id,
            "expected_status": expected_status,
            "rows": rows,
            "history": history[-20:],
        }

    if check_type == "story_event_queue_arc":
        arc_id = str(check.get("arc_id") or "")
        arc = get_story_arc(simulation_state, arc_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = _safe_dict(arc).get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": bool(arc) and not failures,
            "arc_id": arc_id,
            "arc": arc,
            "failures": failures,
        }

    if check_type == "story_event_queue_event_applied":
        event_id = str(check.get("event_id") or "")
        applied = get_applied_story_event(simulation_state, event_id)
        expected_applied = check.get("expected_applied", True)
        return {
            "check_type": check_type,
            "ok": bool(applied) is bool(expected_applied),
            "event_id": event_id,
            "expected_applied": expected_applied,
            "applied": applied,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_event_queue_m25_m27_check_type:{check_type}",
    }


def run_story_event_queue_m25_m27_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_event_queue_m25_m27_check(check=check, result=result, session=session)
        for check in checks
    ]