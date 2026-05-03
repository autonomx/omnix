from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.rules import normalize_escalation_rule
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