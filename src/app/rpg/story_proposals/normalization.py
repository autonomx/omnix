from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.lore.state import normalize_lore_entry
from app.rpg.story_arcs.state import normalize_story_arc
from app.rpg.story_events.validation import ALLOWED_STORY_EVENT_EFFECT_TYPES
from app.rpg.story_proposals.model import STORY_PROPOSAL_VERSION

MAX_PROPOSAL_LORE_ENTRIES = 50
MAX_PROPOSAL_ARCS = 20
MAX_PROPOSAL_EVENTS = 50
MAX_PROPOSAL_ESCALATION_RULES = 50
MAX_EVENT_EFFECTS = 25
MAX_EVENT_PRECONDITIONS = 25
MAX_ARC_LINKS_PER_KIND = 30


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _unique_strs(values: Any, *, limit: int = 50) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_proposal_lore_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_lore_entry(_safe_dict(entry), lore_id=str(_safe_dict(entry).get("lore_id") or ""))


def normalize_proposal_story_arc(arc: Dict[str, Any]) -> Dict[str, Any]:
    arc = normalize_story_arc(_safe_dict(arc), arc_id=str(_safe_dict(arc).get("arc_id") or ""))
    for key in ("linked_lore", "linked_quests", "linked_puzzles", "linked_locations", "linked_entities"):
        arc[key] = _unique_strs(arc.get(key), limit=MAX_ARC_LINKS_PER_KIND)
    return arc


def normalize_proposal_story_event(event: Dict[str, Any]) -> Dict[str, Any]:
    event = _safe_dict(event)
    return {
        "event_id": _safe_str(event.get("event_id")),
        "arc_id": _safe_str(event.get("arc_id")),
        "kind": _safe_str(event.get("kind")) or "event",
        "location_id": _safe_str(event.get("location_id")),
        "require_location": bool(event.get("require_location", False)),
        "participants": _unique_strs(event.get("participants"), limit=20),
        "summary": _safe_str(event.get("summary")),
        "preconditions": [
            dict(row)
            for row in _safe_list(event.get("preconditions"))
            if isinstance(row, dict)
        ][:MAX_EVENT_PRECONDITIONS],
        "effects": [
            dict(row)
            for row in _safe_list(event.get("effects"))
            if isinstance(row, dict)
        ][:MAX_EVENT_EFFECTS],
        "tags": _unique_strs(event.get("tags"), limit=20),
        "metadata": dict(_safe_dict(event.get("metadata"))),
    }


def normalize_proposal_escalation_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    rule = _safe_dict(rule)
    return {
        "rule_id": _safe_str(rule.get("rule_id")),
        "arc_id": _safe_str(rule.get("arc_id")),
        "priority": max(0, min(100, _safe_int(rule.get("priority"), 50))),
        "event": normalize_proposal_story_event(_safe_dict(rule.get("event"))),
        "conditions": [
            dict(row)
            for row in _safe_list(rule.get("conditions"))
            if isinstance(row, dict)
        ][:MAX_EVENT_PRECONDITIONS],
        "cooldown_turns": max(0, _safe_int(rule.get("cooldown_turns"), 0)),
        "max_applications": max(0, _safe_int(rule.get("max_applications"), 1)),
        "pressure_type": _safe_str(rule.get("pressure_type")) or "story",
        "reason": _safe_str(rule.get("reason")),
        "tags": _unique_strs(rule.get("tags"), limit=20),
    }


def normalize_story_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    proposal = _safe_dict(proposal)
    lore_entries = [
        normalize_proposal_lore_entry(row)
        for row in _safe_list(proposal.get("lore_entries"))
        if isinstance(row, dict)
    ][:MAX_PROPOSAL_LORE_ENTRIES]
    story_arcs = [
        normalize_proposal_story_arc(row)
        for row in _safe_list(proposal.get("story_arcs"))
        if isinstance(row, dict)
    ][:MAX_PROPOSAL_ARCS]
    story_events = [
        normalize_proposal_story_event(row)
        for row in _safe_list(proposal.get("story_events"))
        if isinstance(row, dict)
    ][:MAX_PROPOSAL_EVENTS]
    escalation_rules = [
        normalize_proposal_escalation_rule(row)
        for row in _safe_list(proposal.get("escalation_rules"))
        if isinstance(row, dict)
    ][:MAX_PROPOSAL_ESCALATION_RULES]
    return {
        "proposal_version": _safe_str(proposal.get("proposal_version")) or STORY_PROPOSAL_VERSION,
        "proposal_type": _safe_str(proposal.get("proposal_type")) or "story_pack",
        "proposal_id": _safe_str(proposal.get("proposal_id")),
        "title": _safe_str(proposal.get("title")),
        "lore_entries": lore_entries,
        "story_arcs": story_arcs,
        "story_events": story_events,
        "escalation_rules": escalation_rules,
        "metadata": dict(_safe_dict(proposal.get("metadata"))),
        "limits": {
            "max_lore_entries": MAX_PROPOSAL_LORE_ENTRIES,
            "max_story_arcs": MAX_PROPOSAL_ARCS,
            "max_story_events": MAX_PROPOSAL_EVENTS,
            "max_escalation_rules": MAX_PROPOSAL_ESCALATION_RULES,
            "max_event_effects": MAX_EVENT_EFFECTS,
            "allowed_effect_types": sorted(ALLOWED_STORY_EVENT_EFFECT_TYPES),
        },
    }