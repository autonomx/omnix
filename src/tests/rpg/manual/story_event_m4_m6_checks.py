from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.lore.state import get_lore_entry
from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.quests.state import get_quest
from app.rpg.social.reputation import get_relationship
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_events.state import get_applied_story_event
from app.rpg.story_events.validation import validate_story_event


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
        if isinstance(candidate.get("story_event_state"), dict):
            return candidate
    return first_non_empty


def run_story_event_m4_m6_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_event_applied":
        event_id = str(check.get("event_id") or "")
        applied = get_applied_story_event(simulation_state, event_id)
        return {
            "check_type": check_type,
            "ok": bool(applied),
            "event_id": event_id,
            "applied": applied,
        }

    if check_type == "story_event_validation":
        event = _safe_dict(check.get("event"))
        expected_ok = bool(check.get("expected_ok"))
        validation = validate_story_event(simulation_state, event)
        return {
            "check_type": check_type,
            "ok": bool(validation.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(validation.get("ok")),
            "validation": validation,
        }

    if check_type == "story_event_arc":
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

    if check_type == "story_event_lore":
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

    if check_type == "story_event_memory":
        subject_id = str(check.get("subject_id") or "")
        expected_event_id = str(check.get("expected_event_id") or "")
        rows = retrieve_causal_memories(
            simulation_state,
            subject_id,
            actor_id=check.get("actor_id"),
            target_id=check.get("target_id"),
            tags=check.get("tags") or [],
            max_items=10,
        )
        event_ids = [row.get("event_id") for row in rows]
        return {
            "check_type": check_type,
            "ok": expected_event_id in event_ids,
            "subject_id": subject_id,
            "expected_event_id": expected_event_id,
            "actual_event_ids": event_ids,
            "retrieved": rows,
        }

    if check_type == "story_event_social":
        npc_id = str(check.get("npc_id") or "")
        relationship = get_relationship(simulation_state, npc_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = relationship.get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": not failures,
            "npc_id": npc_id,
            "relationship": relationship,
            "failures": failures,
        }

    if check_type == "story_event_quest":
        quest_id = str(check.get("quest_id") or "")
        quest = get_quest(simulation_state, quest_id)
        expected = _safe_dict(check.get("expected"))
        failures = {}
        for key, expected_value in expected.items():
            actual = _safe_dict(quest).get(key)
            if actual != expected_value:
                failures[key] = {"expected": expected_value, "actual": actual}
        return {
            "check_type": check_type,
            "ok": bool(quest) and not failures,
            "quest_id": quest_id,
            "quest": quest,
            "failures": failures,
        }

    if check_type == "story_event_world_event":
        source_story_event_id = str(check.get("source_story_event_id") or "")
        world_state = _safe_dict(simulation_state.get("world_event_state"))
        rows = [
            row
            for row in world_state.get("events") or []
            if isinstance(row, dict)
            and row.get("source_story_event_id") == source_story_event_id
        ]
        return {
            "check_type": check_type,
            "ok": bool(rows),
            "source_story_event_id": source_story_event_id,
            "rows": rows[:10],
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_event_m4_m6_check_type:{check_type}",
    }


def run_story_event_m4_m6_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_event_m4_m6_check(check=check, result=result, session=session)
        for check in checks
    ]