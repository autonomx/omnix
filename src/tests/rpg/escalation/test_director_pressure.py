from app.rpg.escalation.director import build_director_pressure
from app.rpg.story_arcs.state import get_story_arc, start_story_arc


def test_director_pressure_lists_high_priority_arc_without_applying():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=80)
    rules = [
        {
            "rule_id": "rule:bandit_warning",
            "arc_id": "arc:bandit_pressure",
            "priority": 70,
            "pressure_type": "threat",
            "reason": "bandit pressure high",
            "conditions": [
                {
                    "type": "arc_pressure_at_least",
                    "arc_id": "arc:bandit_pressure",
                    "minimum": 50,
                }
            ],
            "event": {
                "event_id": "event:bandits_warn_bran",
                "kind": "warning",
                "summary": "Bandits warned Bran.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "threat"}
                ],
            },
        }
    ]

    result = build_director_pressure(simulation_state, rules, turn_index=3)

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["director_pressure"][0]["eligible_event_id"] == "event:bandits_warn_bran"
    assert result["applied_events"] == []
    assert arc["stage"] == "rumors"


def test_director_pressure_is_bounded():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=90)
    rules = []
    for i in range(20):
        rules.append(
            {
                "rule_id": f"rule:{i}",
                "arc_id": "arc:bandit_pressure",
                "priority": i,
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    }
                ],
                "event": {"event_id": f"event:{i}", "effects": []},
            }
        )

    result = build_director_pressure(simulation_state, rules, max_items=5)

    assert len(result["director_pressure"]) == 5
    assert result["eligible_count"] == 20