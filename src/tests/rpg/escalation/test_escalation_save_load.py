import json

from app.rpg.escalation.state import mark_escalation_rule_applied, normalize_escalation_state


def test_escalation_state_json_roundtrip():
    simulation_state = {}
    mark_escalation_rule_applied(
        simulation_state,
        rule_id="rule:bandit_warning",
        arc_id="arc:bandit_pressure",
        event_id="event:bandits_warn_bran",
        turn_index=4,
    )

    encoded = json.dumps(simulation_state["escalation_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_escalation_state(decoded)

    row = normalized["rule_applications"]["rule:bandit_warning"]
    assert row["application_count"] == 1
    assert row["last_applied_turn"] == 4
    assert row["applied_event_ids"] == ["event:bandits_warn_bran"]