from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.dialogue_context.arc_context import build_arc_dialogue_context
from app.rpg.dialogue_context.rumors import propagate_rumor
from app.rpg.lore.state import get_lore_entry
from app.rpg.memory.causal_retrieval import retrieve_causal_memories


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


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
            or isinstance(candidate.get("causal_memory_state"), dict)
            or isinstance(candidate.get("memory_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_dialogue_m16_m18_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "dialogue_context":
        npc_id = str(check.get("npc_id") or "")
        context = build_arc_dialogue_context(
            simulation_state,
            npc_id,
            arc_id=str(check.get("arc_id") or ""),
            topic_lore_id=str(check.get("topic_lore_id") or ""),
        )
        expected_can_discuss = check.get("expected_can_discuss")
        expected_lore_id = check.get("expected_lore_id")
        expected_arc_id = check.get("expected_arc_id")
        expected_must_mark_as_rumor = check.get("expected_must_mark_as_rumor")

        ok = True
        if expected_can_discuss is not None:
            ok = ok and context.get("can_discuss") is bool(expected_can_discuss)
        if expected_lore_id:
            ok = ok and expected_lore_id in [row.get("lore_id") for row in context.get("known_lore") or []]
        if expected_arc_id:
            ok = ok and expected_arc_id in [row.get("arc_id") for row in context.get("known_story_arcs") or []]
        if expected_must_mark_as_rumor is not None:
            ok = ok and context.get("rumor_permissions", {}).get("must_mark_as_rumor") is bool(expected_must_mark_as_rumor)

        return {
            "check_type": check_type,
            "ok": ok,
            "npc_id": npc_id,
            "context": context,
            "expected_can_discuss": expected_can_discuss,
            "expected_lore_id": expected_lore_id,
            "expected_arc_id": expected_arc_id,
            "expected_must_mark_as_rumor": expected_must_mark_as_rumor,
        }

    if check_type == "rumor_propagation":
        propagation = propagate_rumor(
            simulation_state,
            speaker_id=str(check.get("speaker_id") or ""),
            lore_id=str(check.get("lore_id") or ""),
            summary=str(check.get("summary") or ""),
            explicit_hearers=check.get("explicit_hearers"),
            turn_index=int(check.get("turn_index") or 1),
        )
        expected_ok = check.get("expected_ok")
        expected_hearer = check.get("expected_hearer")
        expected_truth_promoted = check.get("expected_truth_promoted")
        ok = True
        if expected_ok is not None:
            ok = ok and propagation.get("ok") is bool(expected_ok)
        if expected_hearer:
            ok = ok and expected_hearer in propagation.get("hearers", [])
        if expected_truth_promoted is not None:
            ok = ok and propagation.get("truth_promoted") is bool(expected_truth_promoted)
        return {
            "check_type": check_type,
            "ok": ok,
            "propagation": propagation,
            "expected_ok": expected_ok,
            "expected_hearer": expected_hearer,
            "expected_truth_promoted": expected_truth_promoted,
        }

    if check_type == "rumor_memory":
        subject_id = str(check.get("subject_id") or "")
        expected_lore_id = str(check.get("expected_lore_id") or "")
        rows = retrieve_causal_memories(
            simulation_state,
            subject_id,
            tags=check.get("tags") or ["rumor"],
            max_items=10,
        )
        matched = []
        for row in rows:
            facts = _safe_dict(row.get("facts"))
            if facts.get("lore_id") == expected_lore_id or _safe_str(row.get("lore_id")) == expected_lore_id:
                matched.append(row)
        return {
            "check_type": check_type,
            "ok": bool(matched),
            "subject_id": subject_id,
            "expected_lore_id": expected_lore_id,
            "matched": matched,
            "retrieved": rows,
        }

    if check_type == "rumor_truth_status":
        lore_id = str(check.get("lore_id") or "")
        expected_truth_status = str(check.get("expected_truth_status") or "")
        entry = get_lore_entry(simulation_state, lore_id)
        actual = str((_safe_dict(entry)).get("truth_status") or "")
        return {
            "check_type": check_type,
            "ok": actual == expected_truth_status,
            "lore_id": lore_id,
            "expected_truth_status": expected_truth_status,
            "actual_truth_status": actual,
            "entry": entry,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_dialogue_m16_m18_check_type:{check_type}",
    }


def run_dialogue_m16_m18_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_dialogue_m16_m18_check(check=check, result=result, session=session)
        for check in checks
    ]