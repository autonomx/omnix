from app.rpg.lore.state import get_lore_entry, upsert_lore_entry
from app.rpg.story_arcs.state import get_story_arc, start_story_arc
from app.rpg.story_arcs.transitions import apply_story_arc_transition


def test_story_arc_start_transition():
    simulation_state = {}
    result = apply_story_arc_transition(
        simulation_state,
        {
            "action": "start",
            "arc_id": "arc:bandit_pressure",
            "title": "Bandit Pressure",
            "stage": "rumors",
            "pressure": 20,
            "links": {"lore": ["lore:red_sashes"]},
        },
        turn_index=1,
    )

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert result["ok"] is True
    assert arc["stage"] == "rumors"
    assert arc["pressure"] == 20
    assert "lore:red_sashes" in arc["linked_lore"]


def test_story_arc_stage_advances_when_pressure_threshold_met():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)
    result = apply_story_arc_transition(
        simulation_state,
        {
            "action": "set_stage",
            "arc_id": "arc:bandit_pressure",
            "stage": "threat",
            "conditions": [
                {"type": "arc_pressure_at_least", "arc_id": "arc:bandit_pressure", "minimum": 50}
            ],
        },
    )

    assert result["ok"] is True
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "threat"


def test_story_arc_transition_blocked_by_condition():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=20)
    result = apply_story_arc_transition(
        simulation_state,
        {
            "action": "set_stage",
            "arc_id": "arc:bandit_pressure",
            "stage": "threat",
            "conditions": [
                {"type": "arc_pressure_at_least", "arc_id": "arc:bandit_pressure", "minimum": 50}
            ],
        },
    )

    assert result["ok"] is False
    assert result["reason"] == "conditions_failed"
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "rumors"


def test_story_arc_reveal_lore_transition():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:red_sashes", "title": "The Red Sashes"})
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = apply_story_arc_transition(
        simulation_state,
        {
            "action": "reveal_lore",
            "arc_id": "arc:bandit_pressure",
            "lore_id": "lore:red_sashes",
        },
    )

    assert result["ok"] is True
    assert get_lore_entry(simulation_state, "lore:red_sashes")["revealed_to_player"] is True