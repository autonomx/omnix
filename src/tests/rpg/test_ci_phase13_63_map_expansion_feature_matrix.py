from app.rpg.interactive_cli_travel_response_quality import apply_travel_state_to_matrix_result
from tests.rpg import interactive_feature_matrix as feature_matrix


class _MapExpansionScenario:
    scenario_id = "map_expansion_probe"
    title = "Map expansion: travel beyond the seeded local route"
    commands = (
        "I leave the tavern and take the road north.",
        "I continue toward the old mill.",
        "I keep following the old road east toward the river town.",
    )


def _turn_summary():
    diagnostics = {
        "final_classification": {
            "action_type": "general",
            "requested_terms": [],
            "target_npc": "",
        }
    }
    return {
        "player_input": "",
        "raw_result": {
            "narration": "The moment responds without producing a major new consequence.",
            "interactive_cli_intent_diagnostics": diagnostics,
        },
        "raw_narration": "The moment responds without producing a major new consequence.",
        "interactive_cli_intent_diagnostics": diagnostics,
    }


def test_phase13_63_feature_matrix_includes_map_expansion_probe_without_known_gap():
    scenario_ids = {scenario.scenario_id for scenario in feature_matrix.default_feature_matrix_scenarios()}

    assert "map_expansion_probe" in scenario_ids
    assert "map_expansion_probe" not in feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS
    assert feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS == frozenset()


def test_phase13_63_map_expansion_probe_attaches_canonical_expansion_state():
    result = {
        "results": [
            {
                "scenario": _MapExpansionScenario(),
                "result": {"turns": [_turn_summary(), _turn_summary(), _turn_summary()]},
            }
        ]
    }

    cleanup = apply_travel_state_to_matrix_result(result)

    assert cleanup["changed_turns"] == 3
    turns = result["results"][0]["result"]["turns"]
    expansion_turn = turns[2]
    travel_state = expansion_turn["interactive_cli_travel_state"]
    map_state = travel_state["campaign_map_state"]

    assert travel_state["current_location_id"] == "location:river-town"
    assert travel_state["destination_name"] == "river town"
    assert travel_state["direction"] == "east"
    assert travel_state["travel_history"][-1]["map_expanded"] is True
    assert "location:river-town" in travel_state["known_route"]
    assert "location:river-town" in map_state["locations"]
    assert map_state["locations"]["location:river-town"]["name"] == "river town"
    assert map_state["expansions"][-1]["policy"] == "append_on_edge_request"

    final = expansion_turn["interactive_cli_intent_diagnostics"]["final_classification"]
    assert final["action_type"] == "travel"
    assert final["current_location_id"] == "location:river-town"
    assert final["destination_id"] == "location:river-town"
    assert "river town" in final["requested_terms"]
    assert "east" in final["requested_terms"]
