from app.rpg.escalation.rules import (
    apply_escalation_rule,
    evaluate_escalation_rule,
    evaluate_escalation_rules,
)
from app.rpg.escalation.state import mark_escalation_rule_applied
from app.rpg.quests.state import set_quest_stage, start_quest
from app.rpg.story_arcs.state import get_story_arc, set_story_arc_stage, start_story_arc


def _warning_rule():
    return {
        "rule_id": "rule:bandit_warning",
        "arc_id": "arc:bandit_pressure",
        "priority": 70,
        "pressure_type": "threat",
        "reason": "bandit pressure reached warning threshold",
        "conditions": [
            {
                "type": "arc_pressure_at_least",
                "arc_id": "arc:bandit_pressure",
                "minimum": 50,
            },
            {
                "type": "arc_stage",
                "arc_id": "arc:bandit_pressure",
                "stage": "rumors",
            },
        ],
        "event": {
            "event_id": "event:bandits_warn_bran",
            "kind": "warning",
            "summary": "Bandits warned Bran to pay protection money.",
            "effects": [
                {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "threat"},
                {"type": "world_event_emit"},
            ],
        },
        "cooldown_turns": 3,
        "max_applications": 1,
    }


def test_escalation_rule_ineligible_below_pressure():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=20)

    result = evaluate_escalation_rule(simulation_state, _warning_rule(), turn_index=1)

    assert result["ok"] is True
    assert result["eligible"] is False
    assert result["reason"] == "conditions_failed"


def test_escalation_rule_eligible_at_threshold():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)

    result = evaluate_escalation_rule(simulation_state, _warning_rule(), turn_index=1)

    assert result["ok"] is True
    assert result["eligible"] is True
    assert result["event"]["event_id"] == "event:bandits_warn_bran"


def test_escalation_rule_applies_event_once():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)

    first = apply_escalation_rule(simulation_state, _warning_rule(), turn_index=1)
    second = apply_escalation_rule(simulation_state, _warning_rule(), turn_index=2)

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["evaluation"]["reason"] in {"max_applications_reached", "cooldown_active", "conditions_failed"}
    assert arc["stage"] == "threat"


def test_escalation_rule_respects_cooldown():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)
    rule = _warning_rule()
    rule["max_applications"] = 2
    mark_escalation_rule_applied(
        simulation_state,
        rule_id=rule["rule_id"],
        arc_id=rule["arc_id"],
        event_id="event:previous",
        turn_index=5,
    )

    result = evaluate_escalation_rule(simulation_state, rule, turn_index=6)

    assert result["eligible"] is False
    assert result["reason"] == "cooldown_active"
    assert result["cooldown_remaining"] == 2


def test_resolved_arc_stops_escalating():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)
    set_story_arc_stage(simulation_state, "arc:bandit_pressure", "resolved", status="resolved")

    result = evaluate_escalation_rule(simulation_state, _warning_rule(), turn_index=10)

    assert result["eligible"] is False
    assert result["reason"] == "arc_not_active"


def test_escalation_rule_blocked_by_completed_quest():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)
    start_quest(simulation_state, "quest:stop_red_sashes", stage="investigate")
    set_quest_stage(simulation_state, "quest:stop_red_sashes", "completed", status="completed")
    rule = _warning_rule()
    rule["conditions"].append(
        {
            "type": "quest_status",
            "quest_id": "quest:stop_red_sashes",
            "status": "active",
        }
    )

    result = evaluate_escalation_rule(simulation_state, rule, turn_index=10)

    assert result["eligible"] is False
    assert result["reason"] == "conditions_failed"


def test_evaluate_rules_orders_by_priority():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=80)
    low = _warning_rule()
    low["rule_id"] = "rule:low"
    low["priority"] = 10
    low["event"] = dict(low["event"], event_id="event:low")
    high = _warning_rule()
    high["rule_id"] = "rule:high"
    high["priority"] = 90
    high["event"] = dict(high["event"], event_id="event:high")

    result = evaluate_escalation_rules(simulation_state, [low, high], turn_index=1)

    assert [row["rule"]["rule_id"] for row in result["eligible"]] == ["rule:high", "rule:low"]