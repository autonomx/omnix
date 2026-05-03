from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.story_proposals.validation import validate_story_proposal


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
            isinstance(candidate.get("lore_state"), dict)
            or isinstance(candidate.get("story_arc_state"), dict)
            or isinstance(candidate.get("quest_state"), dict)
            or isinstance(candidate.get("puzzle_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_story_proposal_m10_m12_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_proposal_validation":
        proposal = check.get("proposal")
        expected_ok = bool(check.get("expected_ok"))
        validation = validate_story_proposal(simulation_state, proposal)
        required_error = check.get("required_error")
        ok = bool(validation.get("ok")) is expected_ok
        if required_error:
            ok = ok and required_error in str(validation.get("errors"))
        return {
            "check_type": check_type,
            "ok": ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(validation.get("ok")),
            "required_error": required_error,
            "validation": validation,
        }

    if check_type == "story_proposal_normalized_counts":
        proposal = _safe_dict(check.get("proposal"))
        expected = _safe_dict(check.get("expected"))
        validation = validate_story_proposal(simulation_state, proposal)
        counts = validation.get("result_counts") or {}
        failures = {}
        for key, expected_value in expected.items():
            actual = counts.get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": not failures,
            "validation_ok": bool(validation.get("ok")),
            "counts": counts,
            "failures": failures,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_proposal_m10_m12_check_type:{check_type}",
    }


def run_story_proposal_m10_m12_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_proposal_m10_m12_check(check=check, result=result, session=session)
        for check in checks
    ]