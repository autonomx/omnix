from __future__ import annotations

from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_puzzle_completion_unlocks_quest_gate_setup_order():
    session_id = "manual_service_test_puzzle_quest_setup_order"
    scenario_name = "puzzle_completion_unlocks_quest_gate"
    scenario = build_service_scenarios()[scenario_name]

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name=scenario_name,
    )

    assert ok is True

    session = _ensure_manual_session(session_id)
    simulation_state = session["simulation_state"]

    puzzle = simulation_state["puzzle_state"]["puzzles"]["puzzle:cellar_runes"]
    assert puzzle["flags"]["rune_unlocked"] is True

    quest = simulation_state["quest_state"]["quests"]["quest:rat_cellar"]
    assert quest["stage"] == "runes_unlocked"