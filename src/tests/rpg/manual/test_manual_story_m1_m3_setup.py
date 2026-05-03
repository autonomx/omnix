from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_story_arc_links_to_quest_state_setup_order():
    session_id = "manual_service_test_story_arc_quest_setup_order"
    scenario_name = "story_arc_links_to_quest_state"
    scenario = build_service_scenarios()[scenario_name]

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name=scenario_name,
    )
    assert ok is True

    session = _ensure_manual_session(session_id)
    simulation_state = session["simulation_state"]

    quest = simulation_state["quest_state"]["quests"]["quest:stop_red_sashes"]
    assert quest["stage"] == "investigate"

    arc = simulation_state["story_arc_state"]["arcs"]["arc:bandit_pressure"]
    assert "quest:stop_red_sashes" in arc["linked_quests"]
    assert arc["flags"]["quest_linked"] is True