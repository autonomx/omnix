from __future__ import annotations

from typing import Any, Dict, List, Set

from app.rpg.lore.state import VALID_TRUTH_STATUSES, get_lore_entry
from app.rpg.story_events.validation import ALLOWED_STORY_EVENT_EFFECT_TYPES
from app.rpg.story_proposals.model import STORY_PROPOSAL_VERSION
from app.rpg.story_proposals.normalization import (
    MAX_EVENT_EFFECTS,
    MAX_PROPOSAL_ARCS,
    MAX_PROPOSAL_ESCALATION_RULES,
    MAX_PROPOSAL_EVENTS,
    MAX_PROPOSAL_LORE_ENTRIES,
    normalize_story_proposal,
)
from app.rpg.story_proposals.reference_index import build_story_reference_index


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _err(reason: str, **kwargs: Any) -> Dict[str, Any]:
    return {"reason": reason, **kwargs}


def _check_duplicate_ids(rows: List[Dict[str, Any]], id_key: str, label: str) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    errors = []
    for row in rows:
        row_id = str(row.get(id_key) or "")
        if not row_id:
            errors.append(_err("missing_id", label=label, id_key=id_key))
            continue
        if row_id in seen:
            errors.append(_err("duplicate_id", label=label, id_key=id_key, value=row_id))
        seen.add(row_id)
    return errors


def validate_story_proposal_lore(
    simulation_state: Dict[str, Any],
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    entry = _safe_dict(entry)
    errors = []
    lore_id = _safe_str(entry.get("lore_id"))
    if not lore_id:
        errors.append(_err("missing_lore_id"))
    truth_status = _safe_str(entry.get("truth_status")) or "unknown"
    if truth_status not in VALID_TRUTH_STATUSES:
        errors.append(_err("invalid_truth_status", lore_id=lore_id, truth_status=truth_status))

    existing = get_lore_entry(simulation_state, lore_id) if lore_id else None
    if existing and existing.get("truth_status") == "true" and truth_status in {"false", "myth"}:
        errors.append(
            _err(
                "contradicts_existing_true_lore",
                lore_id=lore_id,
                existing_truth_status=existing.get("truth_status"),
                proposed_truth_status=truth_status,
            )
        )

    if truth_status == "secret" and entry.get("revealed_to_player") is True:
        errors.append(_err("secret_lore_revealed_by_default", lore_id=lore_id))

    return {
        "ok": not errors,
        "kind": "lore",
        "lore_id": lore_id,
        "errors": errors,
    }


def validate_story_proposal_arc(
    simulation_state: Dict[str, Any],
    arc: Dict[str, Any],
    *,
    refs: Dict[str, Set[str]] | None = None,
) -> Dict[str, Any]:
    arc = _safe_dict(arc)
    refs = refs or build_story_reference_index(simulation_state, {"story_arcs": [arc]})
    errors = []
    arc_id = _safe_str(arc.get("arc_id"))
    if not arc_id:
        errors.append(_err("missing_arc_id"))

    pressure = int(arc.get("pressure") or 0)
    if pressure < 0 or pressure > 100:
        errors.append(_err("pressure_out_of_bounds", arc_id=arc_id, pressure=pressure))

    status = _safe_str(arc.get("status")) or "inactive"
    if status not in {"inactive", "active", "resolved", "failed"}:
        errors.append(_err("invalid_arc_status", arc_id=arc_id, status=status))

    for lore_id in _safe_list(arc.get("linked_lore")):
        if str(lore_id) not in refs["lore_ids"]:
            errors.append(_err("unknown_lore_reference", arc_id=arc_id, lore_id=str(lore_id)))
    for quest_id in _safe_list(arc.get("linked_quests")):
        # Quest links may seed future quests later, but must be explicitly namespaced.
        if not str(quest_id).startswith("quest:"):
            errors.append(_err("invalid_quest_reference", arc_id=arc_id, quest_id=str(quest_id)))
    for puzzle_id in _safe_list(arc.get("linked_puzzles")):
        if not str(puzzle_id).startswith("puzzle:"):
            errors.append(_err("invalid_puzzle_reference", arc_id=arc_id, puzzle_id=str(puzzle_id)))

    return {
        "ok": not errors,
        "kind": "story_arc",
        "arc_id": arc_id,
        "errors": errors,
    }


def _validate_effect_references(
    effect: Dict[str, Any],
    *,
    refs: Dict[str, Set[str]],
    event_id: str,
) -> List[Dict[str, Any]]:
    errors = []
    effect_type = _safe_str(effect.get("type"))
    if effect_type not in ALLOWED_STORY_EVENT_EFFECT_TYPES:
        return [_err("unknown_effect_type", event_id=event_id, effect_type=effect_type)]

    arc_id = _safe_str(effect.get("arc_id"))
    if effect_type in {"arc_pressure_delta", "arc_stage_set", "arc_flag_set"} and arc_id and arc_id not in refs["arc_ids"]:
        errors.append(_err("unknown_arc_reference", event_id=event_id, effect_type=effect_type, arc_id=arc_id))

    if effect_type == "arc_pressure_delta":
        delta = int(effect.get("delta") or 0)
        if delta < -100 or delta > 100:
            errors.append(_err("pressure_delta_out_of_bounds", event_id=event_id, delta=delta))

    lore_id = _safe_str(effect.get("lore_id"))
    if effect_type in {"lore_reveal", "lore_truth_status_set", "lore_known_by_add", "lore_tag_add"}:
        if lore_id not in refs["lore_ids"]:
            errors.append(_err("unknown_lore_reference", event_id=event_id, effect_type=effect_type, lore_id=lore_id))

    if effect_type == "lore_truth_status_set":
        truth_status = _safe_str(effect.get("truth_status"))
        if truth_status not in VALID_TRUTH_STATUSES:
            errors.append(_err("invalid_truth_status", event_id=event_id, truth_status=truth_status))

    if effect_type == "social_delta":
        npc_id = _safe_str(effect.get("npc_id"))
        if not npc_id:
            errors.append(_err("missing_npc_id", event_id=event_id, effect_type=effect_type))
        for key in ("trust", "fear", "respect", "hostility", "reputation"):
            if key in effect:
                value = int(effect.get(key) or 0)
                if value < -100 or value > 100:
                    errors.append(_err("social_delta_out_of_bounds", event_id=event_id, field=key, value=value))

    if effect_type == "quest_transition":
        transition = _safe_dict(effect.get("transition"))
        quest_id = _safe_str(transition.get("quest_id") or effect.get("quest_id"))
        if quest_id and not quest_id.startswith("quest:"):
            errors.append(_err("invalid_quest_reference", event_id=event_id, quest_id=quest_id))

    if effect_type == "puzzle_transition":
        transition = _safe_dict(effect.get("transition"))
        puzzle_id = _safe_str(transition.get("puzzle_id") or effect.get("puzzle_id"))
        if puzzle_id and not puzzle_id.startswith("puzzle:"):
            errors.append(_err("invalid_puzzle_reference", event_id=event_id, puzzle_id=puzzle_id))

    return errors


def validate_story_proposal_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    refs: Dict[str, Set[str]] | None = None,
) -> Dict[str, Any]:
    event = _safe_dict(event)
    refs = refs or build_story_reference_index(simulation_state, {"story_events": [event]})
    errors = []
    event_id = _safe_str(event.get("event_id"))
    if not event_id:
        errors.append(_err("missing_event_id"))

    arc_id = _safe_str(event.get("arc_id"))
    if arc_id and arc_id not in refs["arc_ids"]:
        errors.append(_err("unknown_arc_reference", event_id=event_id, arc_id=arc_id))

    location_id = _safe_str(event.get("location_id"))
    if event.get("require_location", False) and not location_id:
        errors.append(_err("missing_required_location", event_id=event_id))
    if location_id and refs["location_ids"] and location_id not in refs["location_ids"]:
        errors.append(_err("unknown_location_reference", event_id=event_id, location_id=location_id))

    for participant in _safe_list(event.get("participants")):
        participant = str(participant)
        if refs["entity_ids"] and participant not in refs["entity_ids"]:
            errors.append(_err("unknown_entity_reference", event_id=event_id, entity_id=participant))

    effects = _safe_list(event.get("effects"))
    if len(effects) > MAX_EVENT_EFFECTS:
        errors.append(_err("too_many_effects", event_id=event_id, count=len(effects), max=MAX_EVENT_EFFECTS))
    for effect in effects:
        if isinstance(effect, dict):
            errors.extend(_validate_effect_references(effect, refs=refs, event_id=event_id))

    return {
        "ok": not errors,
        "kind": "story_event",
        "event_id": event_id,
        "errors": errors,
    }


def validate_story_proposal_escalation_rule(
    simulation_state: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    refs: Dict[str, Set[str]] | None = None,
) -> Dict[str, Any]:
    rule = _safe_dict(rule)
    refs = refs or build_story_reference_index(simulation_state, {"escalation_rules": [rule]})
    errors = []
    rule_id = _safe_str(rule.get("rule_id"))
    if not rule_id:
        errors.append(_err("missing_rule_id"))

    arc_id = _safe_str(rule.get("arc_id"))
    if not arc_id:
        errors.append(_err("missing_arc_id"))
    elif arc_id not in refs["arc_ids"]:
        errors.append(_err("unknown_arc_reference", rule_id=rule_id, arc_id=arc_id))

    priority = int(rule.get("priority") or 0)
    if priority < 0 or priority > 100:
        errors.append(_err("priority_out_of_bounds", rule_id=rule_id, priority=priority))

    max_applications = int(rule.get("max_applications") or 0)
    if max_applications < 0 or max_applications > 20:
        errors.append(_err("max_applications_out_of_bounds", rule_id=rule_id, max_applications=max_applications))

    cooldown_turns = int(rule.get("cooldown_turns") or 0)
    if cooldown_turns < 0 or cooldown_turns > 1000:
        errors.append(_err("cooldown_out_of_bounds", rule_id=rule_id, cooldown_turns=cooldown_turns))

    event_result = validate_story_proposal_event(
        simulation_state,
        _safe_dict(rule.get("event")),
        refs=refs,
    )
    if not event_result.get("ok"):
        errors.append(_err("event_invalid", rule_id=rule_id, event_result=event_result))

    return {
        "ok": not errors,
        "kind": "escalation_rule",
        "rule_id": rule_id,
        "errors": errors,
    }


def validate_story_proposal(
    simulation_state: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(proposal, dict):
        normalized = normalize_story_proposal({})
        return {
            "ok": False,
            "proposal_id": "",
            "proposal_version": "",
            "proposal_type": "",
            "errors": [
                {
                    "reason": "invalid_proposal_json",
                    "expected": "object",
                    "actual_type": type(proposal).__name__,
                },
                {
                    "reason": "unsupported_proposal_version",
                    "expected": STORY_PROPOSAL_VERSION,
                    "actual": "",
                },
            ],
            "normalized": normalized,
            "result_counts": {
                "lore_entries": 0,
                "story_arcs": 0,
                "story_events": 0,
                "escalation_rules": 0,
            },
            "validation_results": {
                "lore": [],
                "story_arcs": [],
                "story_events": [],
                "escalation_rules": [],
            },
        }
    raw = _safe_dict(proposal)
    normalized = normalize_story_proposal(raw)
    errors = []

    if normalized["proposal_version"] != STORY_PROPOSAL_VERSION:
        errors.append(
            _err(
                "unsupported_proposal_version",
                expected=STORY_PROPOSAL_VERSION,
                actual=normalized["proposal_version"],
            )
        )
    if normalized["proposal_type"] != "story_pack":
        errors.append(_err("unsupported_proposal_type", actual=normalized["proposal_type"]))

    if len(_safe_list(raw.get("lore_entries"))) > MAX_PROPOSAL_LORE_ENTRIES:
        errors.append(_err("too_many_lore_entries", max=MAX_PROPOSAL_LORE_ENTRIES))
    if len(_safe_list(raw.get("story_arcs"))) > MAX_PROPOSAL_ARCS:
        errors.append(_err("too_many_story_arcs", max=MAX_PROPOSAL_ARCS))
    if len(_safe_list(raw.get("story_events"))) > MAX_PROPOSAL_EVENTS:
        errors.append(_err("too_many_story_events", max=MAX_PROPOSAL_EVENTS))
    if len(_safe_list(raw.get("escalation_rules"))) > MAX_PROPOSAL_ESCALATION_RULES:
        errors.append(_err("too_many_escalation_rules", max=MAX_PROPOSAL_ESCALATION_RULES))

    errors.extend(_check_duplicate_ids(normalized["lore_entries"], "lore_id", "lore"))
    errors.extend(_check_duplicate_ids(normalized["story_arcs"], "arc_id", "story_arc"))
    errors.extend(_check_duplicate_ids(normalized["story_events"], "event_id", "story_event"))
    errors.extend(_check_duplicate_ids(normalized["escalation_rules"], "rule_id", "escalation_rule"))

    refs = build_story_reference_index(simulation_state, normalized)

    lore_results = [
        validate_story_proposal_lore(simulation_state, entry)
        for entry in normalized["lore_entries"]
    ]
    arc_results = [
        validate_story_proposal_arc(simulation_state, arc, refs=refs)
        for arc in normalized["story_arcs"]
    ]
    event_results = [
        validate_story_proposal_event(simulation_state, event, refs=refs)
        for event in normalized["story_events"]
    ]
    rule_results = [
        validate_story_proposal_escalation_rule(simulation_state, rule, refs=refs)
        for rule in normalized["escalation_rules"]
    ]

    for bucket, results in {
        "lore": lore_results,
        "story_arc": arc_results,
        "story_event": event_results,
        "escalation_rule": rule_results,
    }.items():
        for result in results:
            if not result.get("ok"):
                errors.append(_err(f"{bucket}_invalid", result=result))

    return {
        "ok": not errors,
        "proposal_id": normalized.get("proposal_id"),
        "proposal_version": normalized.get("proposal_version"),
        "proposal_type": normalized.get("proposal_type"),
        "errors": errors,
        "normalized": normalized,
        "result_counts": {
            "lore_entries": len(normalized["lore_entries"]),
            "story_arcs": len(normalized["story_arcs"]),
            "story_events": len(normalized["story_events"]),
            "escalation_rules": len(normalized["escalation_rules"]),
        },
        "validation_results": {
            "lore": lore_results,
            "story_arcs": arc_results,
            "story_events": event_results,
            "escalation_rules": rule_results,
        },
    }