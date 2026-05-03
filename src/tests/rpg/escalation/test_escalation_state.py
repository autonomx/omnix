from app.rpg.escalation.state import (
    get_escalation_rule_application,
    mark_escalation_rule_applied,
    normalize_escalation_state,
)


def test_mark_escalation_rule_applied_tracks_count_and_turn():
    simulation_state = {}
    first = mark_escalation_rule_applied(
        simulation_state,
        rule_id="rule:bandit_warning",
        arc_id="arc:bandit_pressure",
        event_id="event:bandit_warning",
        turn_index=5,
    )
    second = mark_escalation_rule_applied(
        simulation_state,
        rule_id="rule:bandit_warning",
        arc_id="arc:bandit_pressure",
        event_id="event:bandit_warning_2",
        turn_index=8,
    )

    application = get_escalation_rule_application(simulation_state, "rule:bandit_warning")
    assert first["ok"] is True
    assert second["ok"] is True
    assert application["application_count"] == 2
    assert application["last_applied_turn"] == 8
    assert application["applied_event_ids"] == ["event:bandit_warning", "event:bandit_warning_2"]


def test_escalation_state_normalizes_json_shape():
    state = normalize_escalation_state(
        {
            "rule_applications": {
                "rule:x": {
                    "application_count": "2",
                    "last_applied_turn": "9",
                    "applied_event_ids": ["event:a"],
                }
            }
        }
    )

    assert state["version"] == 1
    assert state["rule_applications"]["rule:x"]["application_count"] == 2
    assert state["rule_applications"]["rule:x"]["last_applied_turn"] == 9