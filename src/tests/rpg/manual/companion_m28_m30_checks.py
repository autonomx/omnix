from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.companions.offers import (
    accept_companion_offer,
    build_companion_offer_context,
    evaluate_companion_offer,
    refuse_companion_offer,
)
from app.rpg.companions.party import get_party_member
from app.rpg.npc_runtime_context.context import build_npc_runtime_context


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
            isinstance(candidate.get("npc_evolution_state"), dict)
            or isinstance(candidate.get("party_state"), dict)
            or isinstance(candidate.get("social_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_companion_m28_m30_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "companion_offer_evaluate":
        npc_id = str(check.get("npc_id") or "")
        evaluation = evaluate_companion_offer(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            min_trust=int(check.get("min_trust") or 70),
            max_hostility=int(check.get("max_hostility") or 40),
        )
        expected_eligible = check.get("expected_eligible")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_eligible is not None:
            ok = ok and evaluation.get("eligible") is bool(expected_eligible)
        if expected_reason:
            ok = ok and evaluation.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "npc_id": npc_id,
            "evaluation": evaluation,
            "expected_eligible": expected_eligible,
            "expected_reason": expected_reason,
        }

    if check_type == "companion_offer_context":
        npc_id = str(check.get("npc_id") or "")
        context = build_companion_offer_context(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
        )
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = context.get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": not failures,
            "npc_id": npc_id,
            "context": context,
            "failures": failures,
        }

    if check_type == "companion_offer_accept":
        npc_id = str(check.get("npc_id") or "")
        accept_result = accept_companion_offer(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            turn_index=int(check.get("turn_index") or 1),
            min_trust=int(check.get("min_trust") or 70),
            max_hostility=int(check.get("max_hostility") or 40),
        )
        expected_ok = check.get("expected_ok")
        expected_reason = check.get("expected_reason")
        ok = True
        if expected_ok is not None:
            ok = ok and accept_result.get("ok") is bool(expected_ok)
        if expected_reason:
            ok = ok and accept_result.get("reason") == expected_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "npc_id": npc_id,
            "accept_result": accept_result,
            "expected_ok": expected_ok,
            "expected_reason": expected_reason,
        }

    if check_type == "companion_offer_refuse":
        npc_id = str(check.get("npc_id") or "")
        refuse_result = refuse_companion_offer(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            turn_index=int(check.get("turn_index") or 1),
            reason=str(check.get("reason") or "player_refused"),
        )
        expected_ok = check.get("expected_ok")
        ok = True
        if expected_ok is not None:
            ok = ok and refuse_result.get("ok") is bool(expected_ok)
        return {
            "check_type": check_type,
            "ok": ok,
            "npc_id": npc_id,
            "refuse_result": refuse_result,
            "expected_ok": expected_ok,
        }

    if check_type == "party_member":
        npc_id = str(check.get("npc_id") or "")
        member = get_party_member(simulation_state, npc_id)
        expected_present = check.get("expected_present", True)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = _safe_dict(member).get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": (bool(member) is bool(expected_present)) and not failures,
            "npc_id": npc_id,
            "member": member,
            "expected_present": expected_present,
            "failures": failures,
        }

    if check_type == "npc_runtime_context":
        npc_id = str(check.get("npc_id") or "")
        context = build_npc_runtime_context(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            topic_lore_id=str(check.get("topic_lore_id") or ""),
        )
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = context.get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        if "expected_companion_eligible" in check:
            actual = context.get("companion_offer", {}).get("eligible")
            expected_value = bool(check.get("expected_companion_eligible"))
            if actual is not expected_value:
                failures["companion_offer.eligible"] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": not failures,
            "npc_id": npc_id,
            "context": context,
            "failures": failures,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_companion_m28_m30_check_type:{check_type}",
    }


def run_companion_m28_m30_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_companion_m28_m30_check(check=check, result=result, session=session)
        for check in checks
    ]