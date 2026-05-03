from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_dialogue_hostile_social_setup_order():
    session_id = "manual_service_test_dialogue_hostile_social_setup"
    scenario_name = "npc_refuses_arc_topic_if_social_hostile"
    scenario = build_service_scenarios()[scenario_name]

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name=scenario_name,
    )
    assert ok is True

    session = _ensure_manual_session(session_id)
    simulation_state = session.get("simulation_state", {})
    relationship = simulation_state.get("social_state", {}).get("relationships", {}).get("bran", {})
    assert relationship.get("hostility") == 60
    assert relationship.get("trust") == -20