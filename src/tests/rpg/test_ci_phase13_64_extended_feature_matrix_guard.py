"""Phase 13.64 — extended feature matrix scenario guard.

This test keeps the live-provider extended feature suite honest after the
feature-gap cleanup and progressive-map expansion work. It is intentionally
LLM-free for CI; the live-provider ZIP run remains the end-to-end local review
artifact.
"""

from __future__ import annotations

from tests.rpg import interactive_feature_matrix as feature_matrix


EXPECTED_SCENARIO_IDS = (
    "inn_room_purchase_flow",
    "shop_sell_attempt",
    "travel_round_trip_route",
    "map_expansion_probe",
    "npc_memory_recall_probe",
    "equipment_inventory_probe",
    "backed_quest_acceptance_probe",
)


def test_phase13_64_extended_feature_matrix_has_all_current_scenarios() -> None:
    scenarios = feature_matrix.default_feature_matrix_scenarios()
    scenario_ids = tuple(scenario.scenario_id for scenario in scenarios)

    assert scenario_ids == EXPECTED_SCENARIO_IDS
    assert len(scenario_ids) == 7
    assert "map_expansion_probe" in scenario_ids


def test_phase13_64_extended_feature_matrix_has_no_known_gap_exemptions() -> None:
    assert feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS == frozenset()


def test_phase13_64_map_expansion_expectations_are_stateful_travel_terms() -> None:
    scenarios = {
        scenario.scenario_id: scenario
        for scenario in feature_matrix.default_feature_matrix_scenarios()
    }
    map_expansion = scenarios["map_expansion_probe"]

    assert len(map_expansion.commands) == 3
    assert map_expansion.commands[-1] == "I keep following the old road east toward the river town."

    final_expectation = map_expansion.expectations[-1]
    assert final_expectation.final_action_type == "travel"
    assert final_expectation.final_requested_terms_contains_any == (
        "east",
        "river",
        "river town",
    )
    assert "river" in final_expectation.contains_any
    assert "route" in final_expectation.contains_any
