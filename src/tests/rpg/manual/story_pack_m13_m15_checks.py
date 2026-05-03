from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.lore.state import get_lore_entry
from app.rpg.quests.state import get_quest
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_packs.definition_registries import (
    get_escalation_rule_definition,
    get_story_event_definition,
)
from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_packs.registry import get_imported_story_pack


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
        if isinstance(candidate.get("story_pack_state"), dict):
            return candidate
    return first_non_empty


def run_story_pack_m13_m15_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "story_pack_import":
        proposal = _safe_dict(check.get("proposal"))
        expected_ok = bool(check.get("expected_ok"))
        import_result = import_story_pack(
            simulation_state,
            proposal,
            turn_index=int(check.get("turn_index") or 1),
            starter_quests=check.get("starter_quests"),
        )
        required_reason = check.get("required_reason")
        ok = bool(import_result.get("ok")) is expected_ok
        if required_reason:
            ok = ok and import_result.get("reason") == required_reason
        return {
            "check_type": check_type,
            "ok": ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(import_result.get("ok")),
            "required_reason": required_reason,
            "import_result": import_result,
        }

    if check_type == "story_pack_imported":
        pack_id = str(check.get("pack_id") or "")
        imported = get_imported_story_pack(simulation_state, pack_id)
        return {
            "check_type": check_type,
            "ok": bool(imported),
            "pack_id": pack_id,
            "imported": imported,
        }

    if check_type == "story_pack_lore":
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

    if check_type == "story_pack_arc":
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

    if check_type == "story_pack_event_definition":
        event_id = str(check.get("event_id") or "")
        event = get_story_event_definition(simulation_state, event_id)
        return {
            "check_type": check_type,
            "ok": bool(event),
            "event_id": event_id,
            "event": event,
        }

    if check_type == "story_pack_rule_definition":
        rule_id = str(check.get("rule_id") or "")
        rule = get_escalation_rule_definition(simulation_state, rule_id)
        return {
            "check_type": check_type,
            "ok": bool(rule),
            "rule_id": rule_id,
            "rule": rule,
        }

    if check_type == "story_pack_quest":
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

    if check_type == "story_pack_debug_bounded":
        pack_state = _safe_dict(simulation_state.get("story_pack_state"))
        imported_packs = _safe_dict(pack_state.get("imported_packs"))
        event_registry = _safe_dict(simulation_state.get("story_event_registry"))
        rule_registry = _safe_dict(simulation_state.get("escalation_rule_registry"))
        max_packs = int(check.get("max_packs") or 20)
        ok = len(imported_packs) <= max_packs
        return {
            "check_type": check_type,
            "ok": ok,
            "imported_pack_count": len(imported_packs),
            "max_packs": max_packs,
            "event_definition_count": len(_safe_dict(event_registry.get("events"))),
            "rule_definition_count": len(_safe_dict(rule_registry.get("rules"))),
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_story_pack_m13_m15_check_type:{check_type}",
    }


def run_story_pack_m13_m15_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_story_pack_m13_m15_check(check=check, result=result, session=session)
        for check in checks
    ]