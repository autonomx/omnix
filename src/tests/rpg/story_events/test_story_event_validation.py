from app.rpg.lore.state import upsert_lore_entry
from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_events.validation import validate_story_event, validate_story_event_effect


def test_story_event_rejects_unknown_effect_type():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = validate_story_event_effect(
        simulation_state,
        {"type": "invent_gold", "amount": 999},
    )

    assert result["ok"] is False
    assert result["reason"] == "unknown_effect_type"


def test_story_event_rejects_missing_arc():
    simulation_state = {}
    result = validate_story_event(
        simulation_state,
        {
            "event_id": "event:bad",
            "arc_id": "arc:missing",
            "effects": [],
        },
    )

    assert result["ok"] is False
    assert any(row["reason"] == "arc_missing" for row in result["errors"])


def test_story_event_rejects_missing_lore_for_reveal():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = validate_story_event(
        simulation_state,
        {
            "event_id": "event:bad_lore",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {"type": "lore_reveal", "lore_id": "lore:missing"},
            ],
        },
    )

    assert result["ok"] is False
    assert result["errors"][0]["reason"] == "effect_invalid"


def test_story_event_validates_preconditions():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="rumors", pressure=60)
    upsert_lore_entry(simulation_state, {"lore_id": "lore:red_sashes", "title": "The Red Sashes"})

    result = validate_story_event(
        simulation_state,
        {
            "event_id": "event:bandit_warning",
            "arc_id": "arc:bandit_pressure",
            "preconditions": [
                {
                    "type": "arc_pressure_at_least",
                    "arc_id": "arc:bandit_pressure",
                    "minimum": 50,
                }
            ],
            "effects": [
                {"type": "lore_reveal", "lore_id": "lore:red_sashes"},
            ],
        },
    )

    assert result["ok"] is True