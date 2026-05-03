import json

from app.rpg.story_arcs.state import (
    apply_story_arc_pressure_delta,
    normalize_story_arc_state,
    set_story_arc_flag,
    start_story_arc,
)


def test_story_arc_state_json_roundtrip():
    simulation_state = {}
    start_story_arc(
        simulation_state,
        "arc:bandit_pressure",
        stage="rumors",
        pressure=20,
        links={"lore": ["lore:red_sashes"], "entity": ["bran"]},
    )
    apply_story_arc_pressure_delta(simulation_state, "arc:bandit_pressure", 15)
    set_story_arc_flag(simulation_state, "arc:bandit_pressure", "bran_warned", True)

    encoded = json.dumps(simulation_state["story_arc_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_story_arc_state(decoded)

    arc = normalized["arcs"]["arc:bandit_pressure"]
    assert arc["pressure"] == 35
    assert arc["flags"]["bran_warned"] is True
    assert "lore:red_sashes" in arc["linked_lore"]
    assert "bran" in arc["linked_entities"]