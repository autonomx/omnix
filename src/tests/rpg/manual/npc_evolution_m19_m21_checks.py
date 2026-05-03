from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.npc_evolution.conditions import evaluate_npc_evolution_condition
from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.npc_evolution.transitions import apply_npc_evolution_transition


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
        if isinstance(candidate.get("npc_evolution_state"), dict):
            return candidate
    return first_non_empty


def run_npc_evolution_m19_m21_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "npc_evolution":
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

    if check_type == "npc_evolution_condition":
        condition = _safe_dict(check.get("condition"))
        expected_ok = bool(check.get("expected_ok"))
        condition_result = evaluate_npc_evolution_condition(simulation_state, condition)
        return {
            "check_type": check_type,
            "ok": bool(condition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(condition_result.get("ok")),
            "condition_result": condition_result,
        }

    if check_type == "npc_evolution_transition":
        transition = _safe_dict(check.get("transition"))
        expected_ok = bool(check.get("expected_ok"))
        transition_result = apply_npc_evolution_transition(
            simulation_state,
            transition,
            turn_index=int(check.get("turn_index") or 1),
        )
        return {
            "check_type": check_type,
            "ok": bool(transition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(transition_result.get("ok")),
            "transition_result": transition_result,
        }

    if check_type == "npc_evolution_debug_bounded":
        npc_id = str(check.get("npc_id") or "")
        evolution = get_npc_evolution(simulation_state, npc_id)
        max_history = int(check.get("max_history") or 50)
        history_count = len((_safe_dict(evolution)).get("history") or [])
        return {
            "check_type": check_type,
            "ok": history_count <= max_history,
            "npc_id": npc_id,
            "history_count": history_count,
            "max_history": max_history,
            "evolution": evolution,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_npc_evolution_m19_m21_check_type:{check_type}",
    }


def run_npc_evolution_m19_m21_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_npc_evolution_m19_m21_check(check=check, result=result, session=session)
        for check in checks
    ]