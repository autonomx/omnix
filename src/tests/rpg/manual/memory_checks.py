from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.memory.causal_retrieval import retrieve_causal_memories


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
    for candidate in [
        result.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        nested.get("simulation_state"),
        _safe_dict(nested.get("session")).get("simulation_state"),
        session_dict.get("simulation_state"),
    ]:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate
    return {}


def run_memory_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "memory_retrieval":
        subject_id = str(check.get("subject_id") or "")
        expected_event_ids = set(check.get("expected_event_ids") or [])
        forbidden_event_ids = set(check.get("forbidden_event_ids") or [])
        rows = retrieve_causal_memories(
            simulation_state,
            subject_id,
            actor_id=check.get("actor_id"),
            target_id=check.get("target_id"),
            location_id=check.get("location_id"),
            tags=check.get("tags") or [],
            query_text=check.get("query_text"),
            max_items=int(check.get("max_items") or 5),
        )
        actual_event_ids = {str(row.get("event_id")) for row in rows}
        ok = expected_event_ids <= actual_event_ids and not (
            forbidden_event_ids & actual_event_ids
        )
        return {
            "check_type": check_type,
            "ok": ok,
            "subject_id": subject_id,
            "expected_event_ids": sorted(expected_event_ids),
            "forbidden_event_ids": sorted(forbidden_event_ids),
            "actual_event_ids": sorted(actual_event_ids),
            "retrieved": rows,
        }

    if check_type == "memory_count_max":
        subject_id = str(check.get("subject_id") or "")
        max_expected = int(check.get("max_expected") or 0)
        state = _safe_dict(simulation_state.get("npc_memory_state"))
        rows = list(_safe_dict(state.get("memories_by_subject")).get(subject_id) or [])
        return {
            "check_type": check_type,
            "ok": len(rows) <= max_expected,
            "subject_id": subject_id,
            "actual_count": len(rows),
            "max_expected": max_expected,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_memory_check_type:{check_type}",
    }


def run_memory_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_memory_check(check=check, result=result, session=session)
        for check in checks
    ]