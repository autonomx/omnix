from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.state import (
    get_escalation_rule_application,
    mark_escalation_rule_applied,
)
from app.rpg.story_arcs.conditions import evaluate_all_story_arc_conditions
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_events.application import apply_story_event


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_escalation_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    rule = _safe_dict(rule)
    return {
        "rule_id": str(rule.get("rule_id") or ""),
        "arc_id": str(rule.get("arc_id") or ""),
        "priority": max(0, min(100, _safe_int(rule.get("priority"), 50))),
        "event": dict(_safe_dict(rule.get("event"))),
        "conditions": [
            dict(row)
            for row in _safe_list(rule.get("conditions"))
            if isinstance(row, dict)
        ][:25],
        "cooldown_turns": max(0, _safe_int(rule.get("cooldown_turns"), 0)),
        "max_applications": max(0, _safe_int(rule.get("max_applications"), 1)),
        "pressure_type": str(rule.get("pressure_type") or "story"),
        "reason": str(rule.get("reason") or ""),
        "tags": [
            str(tag)
            for tag in _safe_list(rule.get("tags"))
            if str(tag)
        ][:20],
        "metadata": dict(_safe_dict(rule.get("metadata"))),
    }


def _cooldown_remaining(
    application: Dict[str, Any] | None,
    *,
    cooldown_turns: int,
    turn_index: int,
) -> int:
    if not application:
        return 0
    last = application.get("last_applied_turn")
    if last is None:
        return 0
    elapsed = int(turn_index or 0) - int(last or 0)
    return max(0, int(cooldown_turns or 0) - elapsed)


def evaluate_escalation_rule(
    simulation_state: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    rule = normalize_escalation_rule(rule)
    rule_id = rule["rule_id"]
    arc_id = rule["arc_id"]

    if not rule_id:
        return {
            "ok": False,
            "eligible": False,
            "reason": "missing_rule_id",
            "rule": rule,
        }

    if not arc_id:
        return {
            "ok": False,
            "eligible": False,
            "reason": "missing_arc_id",
            "rule": rule,
        }

    arc = get_story_arc(simulation_state, arc_id)
    if not arc:
        return {
            "ok": False,
            "eligible": False,
            "reason": "arc_missing",
            "rule": rule,
        }

    if arc.get("status") in {"resolved", "failed"}:
        return {
            "ok": True,
            "eligible": False,
            "reason": "arc_not_active",
            "rule": rule,
            "arc_status": arc.get("status"),
        }

    if arc.get("status") != "active":
        return {
            "ok": True,
            "eligible": False,
            "reason": "arc_inactive",
            "rule": rule,
            "arc_status": arc.get("status"),
        }

    application = get_escalation_rule_application(simulation_state, rule_id)
    application_count = int((application or {}).get("application_count") or 0)
    max_applications = int(rule.get("max_applications") or 0)
    if max_applications and application_count >= max_applications:
        return {
            "ok": True,
            "eligible": False,
            "reason": "max_applications_reached",
            "rule": rule,
            "application": application,
        }

    cooldown = _cooldown_remaining(
        application,
        cooldown_turns=int(rule.get("cooldown_turns") or 0),
        turn_index=turn_index,
    )
    if cooldown > 0:
        return {
            "ok": True,
            "eligible": False,
            "reason": "cooldown_active",
            "rule": rule,
            "application": application,
            "cooldown_remaining": cooldown,
        }

    condition_result = evaluate_all_story_arc_conditions(
        simulation_state,
        rule.get("conditions") or [],
    )
    if not condition_result.get("ok"):
        return {
            "ok": True,
            "eligible": False,
            "reason": "conditions_failed",
            "rule": rule,
            "conditions": condition_result,
        }

    event = dict(rule.get("event") or {})
    if not event.get("event_id"):
        return {
            "ok": False,
            "eligible": False,
            "reason": "event_missing_event_id",
            "rule": rule,
        }
    event.setdefault("arc_id", arc_id)

    return {
        "ok": True,
        "eligible": True,
        "reason": rule.get("reason") or "eligible",
        "rule": rule,
        "event": event,
        "priority": int(rule.get("priority") or 0),
        "pressure_type": rule.get("pressure_type") or "story",
        "conditions": condition_result,
        "application": application,
    }


def evaluate_escalation_rules(
    simulation_state: Dict[str, Any],
    rules: List[Dict[str, Any]],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    results = [
        evaluate_escalation_rule(simulation_state, rule, turn_index=turn_index)
        for rule in rules
        if isinstance(rule, dict)
    ]
    eligible = [row for row in results if row.get("eligible")]
    eligible.sort(
        key=lambda row: (
            int(row.get("priority") or 0),
            str(row.get("rule", {}).get("rule_id") or ""),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "results": results,
        "eligible": eligible,
        "eligible_count": len(eligible),
    }


def apply_escalation_rule(
    simulation_state: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    evaluation = evaluate_escalation_rule(
        simulation_state,
        rule,
        turn_index=turn_index,
    )
    if not evaluation.get("eligible"):
        return {
            "ok": False,
            "reason": "not_eligible",
            "evaluation": evaluation,
        }

    normalized_rule = evaluation["rule"]
    event = dict(evaluation["event"])
    event_result = apply_story_event(
        simulation_state,
        event,
        turn_index=turn_index,
    )
    if not event_result.get("ok"):
        return {
            "ok": False,
            "reason": "story_event_apply_failed",
            "evaluation": evaluation,
            "event_result": event_result,
        }

    mark_result = mark_escalation_rule_applied(
        simulation_state,
        rule_id=normalized_rule["rule_id"],
        arc_id=normalized_rule["arc_id"],
        event_id=event.get("event_id") or "",
        turn_index=turn_index,
    )
    return {
        "ok": True,
        "reason": "applied",
        "rule_id": normalized_rule["rule_id"],
        "arc_id": normalized_rule["arc_id"],
        "event_id": event.get("event_id"),
        "evaluation": evaluation,
        "event_result": event_result,
        "mark_result": mark_result,
    }