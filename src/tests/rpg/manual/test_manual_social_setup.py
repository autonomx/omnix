from __future__ import annotations

from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_social_setup_persists_manual_results_to_session():
    session_id = "manual_service_test_social_setup_manual_results"
    scenario = build_service_scenarios()["social_persuasion_success_high_trust"]

    session = _ensure_manual_session(session_id)
    assert session

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name="social_persuasion_success_high_trust",
    )
    assert ok is True

    reloaded = _ensure_manual_session(session_id)
    social_state = reloaded.get("simulation_state", {}).get("social_state", {})
    manual_results = social_state.get("manual_results", {})

    assert "discount_room" in manual_results
    assert manual_results["discount_room"]["ok"] is True
    assert manual_results["discount_room"]["kind"] == "persuasion"