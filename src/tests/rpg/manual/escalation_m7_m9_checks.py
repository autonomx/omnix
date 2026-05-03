from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.director import build_director_pressure
from app.rpg.escalation.rules import evaluate_escalation_rule, evaluate_escalation_rules
from app.rpg.escalation.state import get_escalation_rule_application
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
            isinstance(candidate.get("escalation_state"), dict)
            or isinstance(candidate.get("story_arc_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_escalation_m7_m9_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "escalation_rule":
        rule = _safe_dict(check.get("rule"))
        expected_eligible = bool(check.get("expected_eligible"))
        turn_index = int(check.get("turn_index") or 1)
        evaluation = evaluate_escalation_rule(simulation_state, rule, turn_index=turn_index)
        return {
            "check_type": check_type,
            "ok": bool(evaluation.get("eligible")) is expected_eligible,
            "expected_eligible": expected_eligible,
            "actual_eligible": bool(evaluation.get("eligible")),
            "evaluation": evaluation,
        }

    if check_type == "escalation_rules":
        rules = [row for row in check.get("rules") or [] if isinstance(row, dict)]
        turn_index = int(check.get("turn_index") or 1)
        expected_eligible_count = check.get("expected_eligible_count")
        expected_first_rule_id = check.get("expected_first_rule_id")
        evaluation = evaluate_escalation_rules(simulation_state, rules, turn_index=turn_index)
        ok = True
        if expected_eligible_count is not None:
            ok = ok and int(evaluation.get("eligible_count") or 0) == int(expected_eligible_count)
        if expected_first_rule_id:
            first = ((evaluation.get("eligible") or [{}])[0]).get("rule", {}).get("rule_id")
            ok = ok and first == expected_first_rule_id
        return {
            "check_type": check_type,
            "ok": ok,
            "expected_eligible_count": expected_eligible_count,
            "expected_first_rule_id": expected_first_rule_id,
            "evaluation": evaluation,
        }

    if check_type == "director_pressure":
        rules = [row for row in check.get("rules") or [] if isinstance(row, dict)]
        turn_index = int(check.get("turn_index") or 1)
        max_items = int(check.get("max_items") or 10)
        expected_count = check.get("expected_count")
        expected_first_event_id = check.get("expected_first_event_id")
        pressure = build_director_pressure(
            simulation_state,
            rules,
            turn_index=turn_index,
            max_items=max_items,
        )
        rows = pressure.get("director_pressure") or []
        ok = True
        if expected_count is not None:
            ok = ok and len(rows) == int(expected_count)
        if expected_first_event_id:
            first_event_id = (rows[0] if rows else {}).get("eligible_event_id")
            ok = ok and first_event_id == expected_first_event_id
        if check.get("expected_advisory_only") is not None:
            ok = ok and pressure.get("advisory_only") is bool(check.get("expected_advisory_only"))
        return {
            "check_type": check_type,
            "ok": ok,
            "pressure": pressure,
            "expected_count": expected_count,
            "expected_first_event_id": expected_first_event_id,
        }

    if check_type == "escalation_application":
        rule_id = str(check.get("rule_id") or "")
        expected_count = check.get("expected_count")
        application = get_escalation_rule_application(simulation_state, rule_id)
        actual_count = int((application or {}).get("application_count") or 0)
        ok = bool(application)
        if expected_count is not None:
            ok = ok and actual_count == int(expected_count)
        return {
            "check_type": check_type,
            "ok": ok,
            "rule_id": rule_id,
            "expected_count": expected_count,
            "actual_count": actual_count,
            "application": application,
        }

    if check_type == "escalation_arc":
        arc_id = str(check.get("arc_id") or "")
        expected = _safe_dict(check.get("expected"))
        arc = get_story_arc(simulation_state, arc_id)
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

    if check_type == "escalation_event_applied":
        event_id = str(check.get("event_id") or "")
        applied = get_applied_story_event(simulation_state, event_id)
        return {
            "check_type": check_type,
            "ok": bool(applied),
            "event_id": event_id,
            "applied": applied,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_escalation_m7_m9_check_type:{check_type}",
    }


def run_escalation_m7_m9_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_escalation_m7_m9_check(check=check, result=result, session=session)
        for check in checks
    ]