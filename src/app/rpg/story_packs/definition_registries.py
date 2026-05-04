from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.rules import normalize_escalation_rule
from app.rpg.story_packs.activation import list_active_story_pack_ids
from app.rpg.story_proposals.normalization import normalize_proposal_story_event

MAX_STORY_EVENT_DEFINITIONS = 500
MAX_ESCALATION_RULE_DEFINITIONS = 500


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_story_event_registry(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    events = {}
    for event_id, row in _safe_dict(value.get("events")).items():
        event_id = str(event_id or "")
        if not event_id:
            continue
        normalized = normalize_proposal_story_event(dict(_safe_dict(row), event_id=event_id))
        events[event_id] = normalized
    ordered = sorted(events)[-MAX_STORY_EVENT_DEFINITIONS:]
    return {
        "version": 1,
        "events": {event_id: events[event_id] for event_id in ordered},
        "max_events": MAX_STORY_EVENT_DEFINITIONS,
    }


def ensure_story_event_registry(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = normalize_story_event_registry(simulation_state.get("story_event_registry"))
    simulation_state["story_event_registry"] = state
    return state


def register_story_event_definition(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    pack_id: str = "",
) -> Dict[str, Any]:
    state = ensure_story_event_registry(simulation_state)
    event = normalize_proposal_story_event(event)
    event_id = _safe_str(event.get("event_id"))
    if not event_id:
        return {"ok": False, "reason": "missing_event_id"}
    event.setdefault("metadata", {})
    event["metadata"] = dict(_safe_dict(event.get("metadata")))
    if pack_id:
        event["metadata"]["pack_id"] = pack_id
    state.setdefault("events", {})[event_id] = event
    simulation_state["story_event_registry"] = normalize_story_event_registry(state)
    return {
        "ok": True,
        "reason": "story_event_definition_registered",
        "event_id": event_id,
        "event": simulation_state["story_event_registry"]["events"][event_id],
    }


def get_story_event_definition(
    simulation_state: Dict[str, Any],
    event_id: str,
) -> Dict[str, Any] | None:
    state = ensure_story_event_registry(simulation_state)
    return state.get("events", {}).get(event_id)


def normalize_escalation_rule_registry(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    rules = {}
    for rule_id, row in _safe_dict(value.get("rules")).items():
        rule_id = str(rule_id or "")
        if not rule_id:
            continue
        normalized = normalize_escalation_rule(dict(_safe_dict(row), rule_id=rule_id))
        rules[rule_id] = normalized
    ordered = sorted(rules)[-MAX_ESCALATION_RULE_DEFINITIONS:]
    return {
        "version": 1,
        "rules": {rule_id: rules[rule_id] for rule_id in ordered},
        "max_rules": MAX_ESCALATION_RULE_DEFINITIONS,
    }


def ensure_escalation_rule_registry(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = normalize_escalation_rule_registry(simulation_state.get("escalation_rule_registry"))
    simulation_state["escalation_rule_registry"] = state
    return state


def register_escalation_rule_definition(
    simulation_state: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    pack_id: str = "",
) -> Dict[str, Any]:
    state = ensure_escalation_rule_registry(simulation_state)
    rule = normalize_escalation_rule(rule)
    rule_id = _safe_str(rule.get("rule_id"))
    if not rule_id:
        return {"ok": False, "reason": "missing_rule_id"}
    rule.setdefault("metadata", {})
    rule["metadata"] = dict(_safe_dict(rule.get("metadata")))
    if pack_id:
        rule["metadata"]["pack_id"] = pack_id
    state.setdefault("rules", {})[rule_id] = rule
    simulation_state["escalation_rule_registry"] = normalize_escalation_rule_registry(state)
    return {
        "ok": True,
        "reason": "escalation_rule_definition_registered",
        "rule_id": rule_id,
        "rule": simulation_state["escalation_rule_registry"]["rules"][rule_id],
    }


def get_escalation_rule_definition(
    simulation_state: Dict[str, Any],
    rule_id: str,
) -> Dict[str, Any] | None:
    state = ensure_escalation_rule_registry(simulation_state)
    return state.get("rules", {}).get(rule_id)


def list_escalation_rule_definitions(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str = "",
) -> List[Dict[str, Any]]:
    state = ensure_escalation_rule_registry(simulation_state)
    rows = list(state.get("rules", {}).values())
    if arc_id:
        rows = [row for row in rows if row.get("arc_id") == arc_id]
    rows.sort(key=lambda row: (int(row.get("priority") or 0), str(row.get("rule_id") or "")), reverse=True)
    return rows


def list_active_escalation_rule_definitions(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str = "",
) -> List[Dict[str, Any]]:
    """Return escalation rules belonging to active imported story packs only."""
    active_pack_ids = set(list_active_story_pack_ids(simulation_state))
    if not active_pack_ids:
        return []

    # Get all globally registered rules
    state = ensure_escalation_rule_registry(simulation_state)
    all_rules = list(state.get("rules", {}).values())

    # Filter by active pack IDs using metadata
    rows = []
    for rule in all_rules:
        if not isinstance(rule, dict):
            continue
        metadata = _safe_dict(rule.get("metadata"))
        rule_pack_id = str(metadata.get("pack_id") or "")
        if rule_pack_id not in active_pack_ids:
            continue
        if arc_id and str(rule.get("arc_id") or "") != arc_id:
            continue
        rows.append(rule)

    # Deterministic order: highest priority first, then rule id
    rows.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("rule_id") or "")))
    return rows