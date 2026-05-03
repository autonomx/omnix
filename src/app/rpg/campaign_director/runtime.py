from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.escalation.director import build_director_pressure
from app.rpg.escalation.rules import apply_escalation_rule, evaluate_escalation_rules
from app.rpg.story_packs.definition_registries import (
    get_story_event_definition,
    list_escalation_rule_definitions,
)
from app.rpg.campaign_director.state import (
    ensure_campaign_director_state,
    record_campaign_director_tick,
)


SAFE_DIRECTOR_MODES = {"idle", "wait", "listen", "observe", "world_tick", "__ambient_tick__"}
MAX_DIRECTOR_APPLICATIONS_PER_TICK = 1
MAX_DIRECTOR_PRESSURE_ITEMS = 10


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _resolve_registered_rules(
    simulation_state: Dict[str, Any],
    *,
    arc_id: str = "",
) -> List[Dict[str, Any]]:
    return list_escalation_rule_definitions(simulation_state, arc_id=arc_id)


def _hydrate_registered_rule_event(
    simulation_state: Dict[str, Any],
    rule: Dict[str, Any],
) -> Dict[str, Any]:
    rule = dict(_safe_dict(rule))
    event = dict(_safe_dict(rule.get("event")))
    event_id = str(event.get("event_id") or "")
    registered_event = get_story_event_definition(simulation_state, event_id) if event_id else None
    if registered_event:
        # Registered event definitions are authoritative. Rule-local event fields
        # may still provide arc_id/event_id defaults, but do not replace effects.
        hydrated = dict(registered_event)
        hydrated.setdefault("event_id", event_id)
        hydrated.setdefault("arc_id", rule.get("arc_id") or "")
        rule["event"] = hydrated
    else:
        event.setdefault("arc_id", rule.get("arc_id") or "")
        rule["event"] = event
    return rule


def _hydrate_registered_rules(
    simulation_state: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        _hydrate_registered_rule_event(simulation_state, rule)
        for rule in rules
        if isinstance(rule, dict)
    ]


def evaluate_campaign_director_tick(
    simulation_state: Dict[str, Any],
    *,
    mode: str = "idle",
    turn_index: int = 0,
    arc_id: str = "",
    max_pressure_items: int = MAX_DIRECTOR_PRESSURE_ITEMS,
) -> Dict[str, Any]:
    director_state = ensure_campaign_director_state(simulation_state)
    mode = str(mode or "")
    if not director_state.get("enabled", True):
        return {
            "ok": True,
            "eligible": [],
            "eligible_count": 0,
            "director_pressure": [],
            "reason": "director_disabled",
            "safe_mode": False,
            "advisory_only": True,
        }
    if mode not in SAFE_DIRECTOR_MODES:
        return {
            "ok": True,
            "eligible": [],
            "eligible_count": 0,
            "director_pressure": [],
            "reason": "unsafe_mode",
            "mode": mode,
            "safe_modes": sorted(SAFE_DIRECTOR_MODES),
            "safe_mode": False,
            "advisory_only": True,
        }

    registered_rules = _resolve_registered_rules(simulation_state, arc_id=arc_id)
    rules = _hydrate_registered_rules(simulation_state, registered_rules)
    evaluation = evaluate_escalation_rules(
        simulation_state,
        rules,
        turn_index=turn_index,
    )
    pressure = build_director_pressure(
        simulation_state,
        rules,
        turn_index=turn_index,
        max_items=max_pressure_items,
    )
    return {
        "ok": True,
        "reason": "evaluated",
        "mode": mode,
        "turn_index": int(turn_index or 0),
        "safe_mode": True,
        "registered_rule_count": len(registered_rules),
        "eligible": evaluation.get("eligible") or [],
        "eligible_count": int(evaluation.get("eligible_count") or 0),
        "director_pressure": pressure.get("director_pressure") or [],
        "advisory_only": True,
        "evaluation": evaluation,
    }


def apply_campaign_director_tick(
    simulation_state: Dict[str, Any],
    *,
    mode: str = "idle",
    turn_index: int = 0,
    arc_id: str = "",
    max_applications: int = MAX_DIRECTOR_APPLICATIONS_PER_TICK,
) -> Dict[str, Any]:
    evaluation = evaluate_campaign_director_tick(
        simulation_state,
        mode=mode,
        turn_index=turn_index,
        arc_id=arc_id,
    )
    if not evaluation.get("safe_mode"):
        record_campaign_director_tick(
            simulation_state,
            turn_index=turn_index,
            mode=mode,
            eligible_count=0,
            skipped_reasons=[{"reason": evaluation.get("reason"), "mode": mode}],
        )
        return {
            "ok": True,
            "reason": evaluation.get("reason"),
            "mode": mode,
            "applied": [],
            "applied_count": 0,
            "evaluation": evaluation,
        }

    applied = []
    skipped = []
    max_applications = max(0, min(MAX_DIRECTOR_APPLICATIONS_PER_TICK, int(max_applications or 0)))
    eligible = _safe_list(evaluation.get("eligible"))
    for item in eligible:
        if len(applied) >= max_applications:
            skipped.append(
                {
                    "reason": "application_limit_reached",
                    "rule_id": _safe_dict(item.get("rule")).get("rule_id"),
                }
            )
            continue
        rule = _safe_dict(item.get("rule"))
        result = apply_escalation_rule(
            simulation_state,
            rule,
            turn_index=turn_index,
        )
        if result.get("ok"):
            applied.append(result)
        else:
            skipped.append(
                {
                    "reason": "apply_failed",
                    "rule_id": rule.get("rule_id"),
                    "result_reason": result.get("reason"),
                    "result": result,
                }
            )

    record = record_campaign_director_tick(
        simulation_state,
        turn_index=turn_index,
        mode=mode,
        eligible_count=int(evaluation.get("eligible_count") or 0),
        applied_rule_ids=[
            str(row.get("rule_id") or "")
            for row in applied
            if row.get("rule_id")
        ],
        applied_event_ids=[
            str(row.get("event_id") or "")
            for row in applied
            if row.get("event_id")
        ],
        skipped_reasons=skipped,
    )
    return {
        "ok": True,
        "reason": "applied",
        "mode": mode,
        "turn_index": int(turn_index or 0),
        "applied": applied,
        "applied_count": len(applied),
        "skipped": skipped,
        "evaluation": evaluation,
        "record": record,
    }


def build_campaign_director_snapshot(
    simulation_state: Dict[str, Any],
    *,
    mode: str = "idle",
    turn_index: int = 0,
    arc_id: str = "",
) -> Dict[str, Any]:
    state = ensure_campaign_director_state(simulation_state)
    evaluation = evaluate_campaign_director_tick(
        simulation_state,
        mode=mode,
        turn_index=turn_index,
        arc_id=arc_id,
    )
    return {
        "ok": True,
        "campaign_director_state": state,
        "director_pressure": evaluation.get("director_pressure") or [],
        "eligible_count": evaluation.get("eligible_count") or 0,
        "registered_rule_count": evaluation.get("registered_rule_count") or 0,
        "safe_mode": evaluation.get("safe_mode"),
        "advisory_only": True,
        "bounded": {
            "max_pressure_items": MAX_DIRECTOR_PRESSURE_ITEMS,
            "max_applications_per_tick": MAX_DIRECTOR_APPLICATIONS_PER_TICK,
        },
    }