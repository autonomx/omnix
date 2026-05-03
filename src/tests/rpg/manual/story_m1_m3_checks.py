from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.lore.conditions import evaluate_lore_condition
from app.rpg.lore.state import get_lore_entry
from app.rpg.story_arcs.conditions import evaluate_story_arc_condition
from app.rpg.story_arcs.state import get_story_arc


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
        if isinstance(candidate.get("lore_state"), dict) or isinstance(candidate.get("story_arc_state"), dict):
            return candidate
    return first_non_empty


def run_story_m1_m3_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "lore_entry":
        lore_id = str(check.get("lore_id") or "")
        entry = get_lore_entry(simulation_state, lore_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = _safe_dict(entry).get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": bool(entry) and not failures,
            "lore_id": lore_id,
            "entry": entry,
            "failures": failures,
        }

    if check_type == "lore_condition":
        condition = _safe_dict(check.get("condition"))
        expected_ok = bool(check.get("expected_ok"))
        condition_result = evaluate_lore_condition(simulation_state, condition)
        return {
            "check_type": check_type,
            "ok": bool(condition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(condition_result.get("ok")),
            "condition_result": condition_result,
        }

    if check_type == "story_arc":
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
            "arc": _bounded_arc(arc),
            "failures": failures,
        }

    if check_type == "story_arc_condition":
        condition = _safe_dict(check.get("condition"))
        expected_ok = bool(check.get("expected_ok"))
        condition_result = evaluate_story_arc_condition(simulation_state, condition)
        return {
            "check_type": check_type,
            "ok": bool(condition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(condition_result.get("ok")),
            "condition_result": condition_result,
        }

    if check_type == "story_arc_debug_bounded":
        arc_id = str(check.get("arc_id") or "")
        arc = _bounded_arc(get_story_arc(simulation_state, arc_id))
        max_link_count = int(check.get("max_link_count") or 20)
        link_count = (
            len(arc.get("linked_lore") or [])
            + len(arc.get("linked_quests") or [])
            + len(arc.get("linked_puzzles") or [])
            + len(arc.get("linked_locations") or [])
            + len(arc.get("linked_entities") or [])
        )
        return {
            "check_type": check_type,
            "ok": link_count <= max_link_count,
            "arc_id": arc_id,
            "link_count": link_count,
            "max_link_count": max_link_count,
            "arc": arc,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_m1_m3_check_type:{check_type}",
    }


def _bounded_arc(arc: Dict[str, Any] | None) -> Dict[str, Any]:
    arc = _safe_dict(arc)
    if not arc:
        return {}
    return {
        "arc_id": arc.get("arc_id"),
        "title": arc.get("title"),
        "status": arc.get("status"),
        "stage": arc.get("stage"),
        "pressure": arc.get("pressure"),
        "escalation_level": arc.get("escalation_level"),
        "linked_lore": list(arc.get("linked_lore") or [])[:20],
        "linked_quests": list(arc.get("linked_quests") or [])[:20],
        "linked_puzzles": list(arc.get("linked_puzzles") or [])[:20],
        "linked_locations": list(arc.get("linked_locations") or [])[:20],
        "linked_entities": list(arc.get("linked_entities") or [])[:20],
        "flags": dict(arc.get("flags") or {}),
        "started_turn": arc.get("started_turn"),
        "resolved_turn": arc.get("resolved_turn"),
    }


def run_story_m1_m3_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_m1_m3_check(check=check, result=result, session=session)
        for check in checks
    ]