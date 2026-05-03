from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_proposals.validation import validate_story_proposal

from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.scenarios.story_event_queue_m25_m27 import _queue_pack
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_story_event_queue_setup_seeds_pack_arc_and_pending_queue():
    session_id = "manual_service_test_story_event_queue_setup"
    scenario = build_service_scenarios()["story_event_queue_enqueues_without_applying"]

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name="story_event_queue_enqueues_without_applying",
    )
    assert ok is True

    session = _ensure_manual_session(session_id)
    simulation_state = session["simulation_state"]

    assert simulation_state["story_arc_state"]["arcs"]["arc:bandit_pressure"]["stage"] == "rumors"
    assert simulation_state["story_event_queue_state"]["pending"]
    assert simulation_state["story_event_queue_state"]["pending"][0]["event_id"] == "event:delayed_bandit_attack"


def test_story_event_queue_pack_fixture_validates_and_imports():
    simulation_state = {}
    validation = validate_story_proposal(simulation_state, _queue_pack())
    assert validation["ok"] is True, validation

    result = import_story_pack(simulation_state, _queue_pack(), turn_index=1)
    assert result["ok"] is True, result
    assert "arc:bandit_pressure" in simulation_state["story_arc_state"]["arcs"]
    assert "event:delayed_bandit_attack" in simulation_state["story_event_registry"]["events"]