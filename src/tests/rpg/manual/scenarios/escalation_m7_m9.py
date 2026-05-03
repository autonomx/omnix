from __future__ import annotations

from typing import Any, Dict


def _bandit_warning_rule(
    *,
    pressure_min: int = 50,
    stage: str = "rumors",
    event_id: str = "event:bandits_warn_bran",
    priority: int = 70,
    cooldown_turns: int = 3,
    max_applications: int = 1,
) -> Dict[str, Any]:
    return {
        "rule_id": "rule:bandit_warning",
        "arc_id": "arc:bandit_pressure",
        "priority": priority,
        "pressure_type": "threat",
        "reason": "bandit pressure reached warning threshold",
        "conditions": [
            {
                "type": "arc_pressure_at_least",
                "arc_id": "arc:bandit_pressure",
                "minimum": pressure_min,
            },
            {
                "type": "arc_stage",
                "arc_id": "arc:bandit_pressure",
                "stage": stage,
            },
        ],
        "event": {
            "event_id": event_id,
            "arc_id": "arc:bandit_pressure",
            "kind": "warning",
            "location_id": "tavern_common_room",
            "summary": "Bandits warned Bran to pay protection money.",
            "tags": ["bandit", "warning"],
            "effects": [
                {
                    "type": "arc_stage_set",
                    "arc_id": "arc:bandit_pressure",
                    "stage": "threat",
                },
                {"type": "world_event_emit"},
            ],
        },
        "cooldown_turns": cooldown_turns,
        "max_applications": max_applications,
        "tags": ["bandit", "warning"],
    }


ESCALATION_M7_M9_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "escalation_rule_ineligible_below_pressure": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 20}
        ],
        "turns": ["I ignore minor bandit rumors."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": _bandit_warning_rule(),
                "expected_eligible": False,
            }
        ],
    },
    "escalation_rule_eligible_at_threshold": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 60}
        ],
        "turns": ["I ignore serious bandit pressure."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": _bandit_warning_rule(),
                "expected_eligible": True,
            }
        ],
    },
    "escalation_rule_applies_event_once": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 60}
        ],
        "setup_apply_escalation_rules": [_bandit_warning_rule()],
        "turns": ["I let the bandit warning happen."],
        "checks": [
            {
                "type": "escalation_application",
                "rule_id": "rule:bandit_warning",
                "expected_count": 1,
            },
            {
                "type": "escalation_event_applied",
                "event_id": "event:bandits_warn_bran",
            },
            {
                "type": "escalation_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "threat"},
            },
        ],
    },
    "escalation_rule_respects_cooldown": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 60}
        ],
        "setup_escalation_applications": [
            {
                "rule_id": "rule:bandit_warning",
                "arc_id": "arc:bandit_pressure",
                "event_id": "event:previous_warning",
                "turn_index": 5,
            }
        ],
        "turns": ["I check if the warning can repeat immediately."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": dict(_bandit_warning_rule(max_applications=2), turn_index=6),
                "turn_index": 6,
                "expected_eligible": False,
            }
        ],
    },
    "escalation_rule_blocked_by_completed_quest": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 60}
        ],
        "setup_quest_transitions": [
            {"action": "start", "quest_id": "quest:stop_red_sashes", "stage": "investigate"},
            {"action": "set_stage", "quest_id": "quest:stop_red_sashes", "stage": "completed", "status": "completed"},
        ],
        "turns": ["I check whether solved bandit quest blocks escalation."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": dict(
                    _bandit_warning_rule(),
                    conditions=[
                        *_bandit_warning_rule()["conditions"],
                        {
                            "type": "quest_status",
                            "quest_id": "quest:stop_red_sashes",
                            "status": "active",
                        },
                    ],
                ),
                "expected_eligible": False,
            }
        ],
    },
    "director_pressure_lists_high_priority_arc": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 80}
        ],
        "turns": ["I inspect director pressure."],
        "checks": [
            {
                "type": "director_pressure",
                "rules": [_bandit_warning_rule(priority=90)],
                "expected_count": 1,
                "expected_first_event_id": "event:bandits_warn_bran",
                "expected_advisory_only": True,
            }
        ],
    },
    "director_pressure_is_bounded": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 90}
        ],
        "turns": ["I inspect a bounded director pressure list."],
        "checks": [
            {
                "type": "director_pressure",
                "max_items": 3,
                "expected_count": 3,
                "rules": [
                    dict(_bandit_warning_rule(event_id=f"event:warning_{i}", priority=50 + i), rule_id=f"rule:warning_{i}")
                    for i in range(8)
                ],
                "expected_advisory_only": True,
            }
        ],
    },
    "director_pressure_does_not_apply_events_directly": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 80}
        ],
        "turns": ["I inspect director pressure without applying it."],
        "checks": [
            {
                "type": "director_pressure",
                "rules": [_bandit_warning_rule()],
                "expected_count": 1,
                "expected_first_event_id": "event:bandits_warn_bran",
                "expected_advisory_only": True,
            },
            {
                "type": "escalation_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
        ],
    },
    "ignored_arc_pressure_escalates_over_idle_ticks": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 45},
            {"action": "pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 10},
        ],
        "turns": ["I wait and do nothing about the bandits."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": _bandit_warning_rule(),
                "expected_eligible": True,
            },
            {
                "type": "escalation_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 55},
            },
        ],
    },
    "resolved_arc_stops_escalating": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 80},
            {"action": "resolve", "arc_id": "arc:bandit_pressure", "stage": "resolved"},
        ],
        "turns": ["I check whether resolved arcs stop escalating."],
        "checks": [
            {
                "type": "escalation_rule",
                "rule": _bandit_warning_rule(),
                "expected_eligible": False,
            }
        ],
    },
}