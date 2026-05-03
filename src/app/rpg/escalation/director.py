from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.rules import evaluate_escalation_rules


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bounded_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    event = _safe_dict(event)
    return {
        "event_id": event.get("event_id"),
        "arc_id": event.get("arc_id"),
        "kind": event.get("kind"),
        "location_id": event.get("location_id"),
        "summary": event.get("summary"),
        "tags": list(event.get("tags") or [])[:10],
        "effect_count": len(event.get("effects") or []),
    }


def build_director_pressure(
    simulation_state: Dict[str, Any],
    rules: List[Dict[str, Any]],
    *,
    turn_index: int = 0,
    max_items: int = 10,
) -> Dict[str, Any]:
    evaluation = evaluate_escalation_rules(
        simulation_state,
        rules,
        turn_index=turn_index,
    )
    rows = []
    for item in evaluation.get("eligible") or []:
        rule = _safe_dict(item.get("rule"))
        event = _safe_dict(item.get("event"))
        rows.append(
            {
                "rule_id": rule.get("rule_id"),
                "arc_id": rule.get("arc_id"),
                "pressure_type": item.get("pressure_type") or rule.get("pressure_type"),
                "priority": item.get("priority"),
                "eligible_event_id": event.get("event_id"),
                "event": _bounded_event_summary(event),
                "reason": item.get("reason") or rule.get("reason"),
                "tags": list(rule.get("tags") or [])[:10],
            }
        )
    rows = rows[: max(0, int(max_items or 0))]
    return {
        "ok": True,
        "turn_index": int(turn_index or 0),
        "director_pressure": rows,
        "eligible_count": len(evaluation.get("eligible") or []),
        "applied_events": [],
        "advisory_only": True,
    }