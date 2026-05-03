from app.rpg.story_arcs.state import (
    apply_story_arc_pressure_delta,
    get_story_arc,
    link_story_arc,
    set_story_arc_flag,
    set_story_arc_stage,
    start_story_arc,
)


def test_start_story_arc_sets_active_stage_pressure_and_links():
    simulation_state = {}
    result = start_story_arc(
        simulation_state,
        "arc:bandit_pressure",
        title="Bandit Pressure",
        stage="rumors",
        pressure=20,
        links={"lore": ["lore:red_sashes"], "entity": ["bran"]},
        turn_index=1,
    )

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert result["ok"] is True
    assert arc["status"] == "active"
    assert arc["stage"] == "rumors"
    assert arc["pressure"] == 20
    assert "lore:red_sashes" in arc["linked_lore"]
    assert "bran" in arc["linked_entities"]


def test_pressure_delta_clamps():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", pressure=90)
    result = apply_story_arc_pressure_delta(simulation_state, "arc:bandit_pressure", 30)

    assert result["after"] == 100


def test_stage_flag_and_link_updates():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")
    set_story_arc_stage(simulation_state, "arc:bandit_pressure", "threat")
    set_story_arc_flag(simulation_state, "arc:bandit_pressure", "bran_warned", True)
    link_story_arc(simulation_state, "arc:bandit_pressure", "quest", "quest:stop_red_sashes")

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert arc["stage"] == "threat"
    assert arc["flags"]["bran_warned"] is True
    assert "quest:stop_red_sashes" in arc["linked_quests"]