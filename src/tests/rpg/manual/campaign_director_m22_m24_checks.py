from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_director.runtime import (
    apply_campaign_director_tick,
    build_campaign_director_snapshot,
    evaluate_campaign_director_tick,
)
from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.story_arcs.state import get_story_arc
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
            isinstance(candidate.get("campaign_director_state"), dict)
            or isinstance(candidate.get("escalation_rule_registry"), dict)
            or isinstance(candidate.get("story_event_registry"), dict)
        ):
            return candidate
    return first_non_empty


def run_campaign_director_m22_m24_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "campaign_director_evaluate":
        evaluation = evaluate_campaign_director_tick(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            arc_id=str(check.get("arc_id") or ""),
        )
        expected_eligible_count = check.get("expected_eligible_count")
        expected_first_event_id = check.get("expected_first_event_id")
        ok = True
        if expected_eligible_count is not None:
            ok = ok and int(evaluation.get("eligible_count") or 0) == int(expected_eligible_count)
        if expected_first_event_id:
            first = (evaluation.get("director_pressure") or [{}])[0].get("eligible_event_id")
            ok = ok and first == expected_first_event_id
        return {
            "check_type": check_type,
            "ok": ok,
            "evaluation": evaluation,
            "expected_eligible_count": expected_eligible_count,
            "expected_first_event_id": expected_first_event_id,
        }

    if check_type == "campaign_director_apply":
        applied = apply_campaign_director_tick(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            arc_id=str(check.get("arc_id") or ""),
            max_applications=int(check.get("max_applications") or 1),
        )
        expected_applied_count = check.get("expected_applied_count")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_applied_count is not None:
            ok = ok and int(applied.get("applied_count") or 0) == int(expected_applied_count)
        if expected_reason:
            ok = ok and applied.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "applied": applied,
            "expected_applied_count": expected_applied_count,
            "expected_reason": expected_reason,
        }

    if check_type == "campaign_director_snapshot":
        snapshot = build_campaign_director_snapshot(
            simulation_state,
            mode=str(check.get("mode") or "idle"),
            turn_index=int(check.get("turn_index") or 1),
            arc_id=str(check.get("arc_id") or ""),
        )
        expected_advisory_only = check.get("expected_advisory_only")
        max_pressure_items = int(check.get("max_pressure_items") or 10)
        ok = len(snapshot.get("director_pressure") or []) <= max_pressure_items
        if expected_advisory_only is not None:
            ok = ok and snapshot.get("advisory_only") is bool(expected_advisory_only)
        return {
            "check_type": check_type,
            "ok": ok,
            "snapshot": snapshot,
            "expected_advisory_only": expected_advisory_only,
            "max_pressure_items": max_pressure_items,
        }

    if check_type == "campaign_director_arc":
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

    if check_type == "campaign_director_event_applied":
        event_id = str(check.get("event_id") or "")
        applied = get_applied_story_event(simulation_state, event_id)
        return {
            "check_type": check_type,
            "ok": bool(applied),
            "event_id": event_id,
            "applied": applied,
        }

    if check_type == "campaign_director_npc_evolution":
        npc_id = str(check.get("npc_id") or "")
        evolution = get_npc_evolution(simulation_state, npc_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = _safe_dict(evolution).get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": bool(evolution) and not failures,
            "npc_id": npc_id,
            "evolution": evolution,
            "failures": failures,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_campaign_director_m22_m24_check_type:{check_type}",
    }


def run_campaign_director_m22_m24_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_campaign_director_m22_m24_check(check=check, result=result, session=session)
        for check in checks
    ]