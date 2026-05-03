from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.social.leverage import validate_leverage
from app.rpg.social.reputation import get_global_reputation, get_relationship


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

    # Prefer explicit current session state. Turn results can contain compact or
    # partial simulation_state snapshots that do not include manual setup-only
    # diagnostics such as social_state.manual_results.
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
        if isinstance(candidate.get("social_state"), dict):
            return candidate
    return first_non_empty


def _last_social_result(simulation_state: Dict[str, Any], key: str) -> Dict[str, Any]:
    social_state = _safe_dict(simulation_state.get("social_state"))
    manual_results = _safe_dict(social_state.get("manual_results"))
    return _safe_dict(manual_results.get(key))


def _manual_result_keys(simulation_state: Dict[str, Any]) -> list[str]:
    social_state = _safe_dict(simulation_state.get("social_state"))
    manual_results = _safe_dict(social_state.get("manual_results"))
    return sorted(str(key) for key in manual_results.keys())


def run_social_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "social_relationship":
        npc_id = str(check.get("npc_id") or "")
        relationship = get_relationship(simulation_state, npc_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = relationship.get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        minimums = _safe_dict(check.get("minimums"))
        for key, expected_minimum in minimums.items():
            actual = int(relationship.get(key) or 0)
            if actual < int(expected_minimum):
                failures[key] = {"minimum": expected_minimum, "actual": actual}
        maximums = _safe_dict(check.get("maximums"))
        for key, expected_maximum in maximums.items():
            actual = int(relationship.get(key) or 0)
            if actual > int(expected_maximum):
                failures[key] = {"maximum": expected_maximum, "actual": actual}
        return {
            "check_type": check_type,
            "ok": not failures,
            "npc_id": npc_id,
            "relationship": relationship,
            "failures": failures,
        }

    if check_type == "social_global_reputation":
        actor_id = str(check.get("actor_id") or "player")
        actual = get_global_reputation(simulation_state, actor_id)
        expected = check.get("expected")
        maximum = check.get("maximum")
        minimum = check.get("minimum")
        ok = True
        if expected is not None:
            ok = ok and actual == int(expected)
        if maximum is not None:
            ok = ok and actual <= int(maximum)
        if minimum is not None:
            ok = ok and actual >= int(minimum)
        return {
            "check_type": check_type,
            "ok": ok,
            "actor_id": actor_id,
            "actual": actual,
            "expected": expected,
            "minimum": minimum,
            "maximum": maximum,
        }

    if check_type == "social_persuasion_result":
        key = str(check.get("result_key") or "last_persuasion")
        social_result = _last_social_result(simulation_state, key)
        if not social_result:
            return {
                "check_type": check_type,
                "ok": False,
                "error": "social_result_missing",
                "result_key": key,
                "available_result_keys": _manual_result_keys(simulation_state),
                "actual": {},
            }
        expected_ok = check.get("expected_ok")
        ok = bool(social_result)
        if expected_ok is not None:
            ok = ok and bool(social_result.get("ok")) is bool(expected_ok)
        expected_stance = check.get("expected_stance")
        if expected_stance:
            ok = ok and social_result.get("stance") == expected_stance
        return {
            "check_type": check_type,
            "ok": ok,
            "result_key": key,
            "expected_ok": expected_ok,
            "expected_stance": expected_stance,
            "actual": social_result,
        }

    if check_type == "social_intimidation_result":
        key = str(check.get("result_key") or "last_intimidation")
        social_result = _last_social_result(simulation_state, key)
        if not social_result:
            return {
                "check_type": check_type,
                "ok": False,
                "error": "social_result_missing",
                "result_key": key,
                "available_result_keys": _manual_result_keys(simulation_state),
                "actual": {},
            }
        expected_ok = check.get("expected_ok")
        ok = bool(social_result)
        if expected_ok is not None:
            ok = ok and bool(social_result.get("ok")) is bool(expected_ok)
        expected_stance = check.get("expected_stance")
        if expected_stance:
            ok = ok and social_result.get("stance") == expected_stance
        expected_escalation = check.get("expected_escalation")
        if expected_escalation is not None:
            ok = ok and bool(social_result.get("escalation")) is bool(expected_escalation)
        return {
            "check_type": check_type,
            "ok": ok,
            "result_key": key,
            "expected_ok": expected_ok,
            "expected_stance": expected_stance,
            "expected_escalation": expected_escalation,
            "actual": social_result,
        }

    if check_type == "social_leverage_valid":
        npc_id = str(check.get("npc_id") or "")
        leverage_id = str(check.get("leverage_id") or "")
        expected_ok = bool(check.get("expected_ok"))
        validation = validate_leverage(
            simulation_state,
            npc_id,
            leverage_id,
            request=check.get("request"),
        )
        return {
            "check_type": check_type,
            "ok": bool(validation.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(validation.get("ok")),
            "validation": validation,
        }

    if check_type == "social_stance":
        npc_id = str(check.get("npc_id") or "")
        expected_stance = str(check.get("expected_stance") or "")
        relationship = get_relationship(simulation_state, npc_id)
        actual_stance = str(relationship.get("last_stance") or "")
        return {
            "check_type": check_type,
            "ok": actual_stance == expected_stance,
            "npc_id": npc_id,
            "expected_stance": expected_stance,
            "actual_stance": actual_stance,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_social_check_type:{check_type}",
    }


def run_social_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_social_check(check=check, result=result, session=session)
        for check in checks
    ]