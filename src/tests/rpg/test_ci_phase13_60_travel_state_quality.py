from app.rpg.interactive_cli_campaign_map_state import (
    CAMPAIGN_MAP_STATE_PATCH,
    initial_campaign_map_state,
    route_transition_for_command,
)
from app.rpg.interactive_cli_travel_response_quality import apply_travel_state_to_matrix_result
from app.rpg.interactive_cli_travel_state import TRAVEL_STATE_PATCH, advance_travel_state, initial_travel_state


class _Scenario:
    scenario_id = "travel_round_trip_route"
    commands = (
        "I leave the tavern and take the road north.",
        "I continue toward the old mill.",
        "I look around near the old mill.",
        "I head back south toward the tavern.",
    )


def _turn_summary():
    diagnostics = {
        "final_classification": {
            "action_type": "general",
            "target_npc": "",
            "requested_terms": [],
        }
    }
    return {
        "raw_result": {
            "narration": "The moment responds without producing a major new consequence.",
            "interactive_cli_intent_diagnostics": diagnostics,
        },
        "raw_narration": "The moment responds without producing a major new consequence.",
        "interactive_cli_intent_diagnostics": diagnostics,
    }


def test_phase13_60_campaign_map_seed_has_canonical_local_region():
    map_state = initial_campaign_map_state()

    assert map_state["patch"] == CAMPAIGN_MAP_STATE_PATCH
    assert map_state["seed_scope"] == "local_region_seed"
    assert map_state["expansion_policy"] == "append_on_edge_request"
    assert set(map_state["locations"]) >= {
        "location:tavern",
        "location:road-north",
        "location:old-mill",
    }
    assert map_state["discovered_location_ids"] == [
        "location:tavern",
        "location:road-north",
        "location:old-mill",
    ]


def test_phase13_60_campaign_map_expands_for_outward_travel_request():
    map_state = initial_campaign_map_state()

    updated, transition = route_transition_for_command(
        map_state,
        current_location_id="location:old-mill",
        command="I keep following the old road east toward the river town.",
    )

    assert transition["map_expanded"] is True
    assert transition["to_location_id"] == "location:river-town"
    assert updated["locations"]["location:river-town"]["name"] == "river town"
    assert "location:river-town" in updated["discovered_location_ids"]
    assert updated["expansions"][-1]["policy"] == "append_on_edge_request"


def test_phase13_60_travel_state_advances_round_trip_locations():
    state = initial_travel_state()

    state = advance_travel_state(state, "I leave the tavern and take the road north.")
    assert state["previous_location_id"] == "location:tavern"
    assert state["current_location_id"] == "location:road-north"
    assert state["destination_id"] == "location:road-north"
    assert state["direction"] == "north"
    assert state["campaign_map_state"]["patch"] == CAMPAIGN_MAP_STATE_PATCH

    state = advance_travel_state(state, "I continue toward the old mill.")
    assert state["previous_location_id"] == "location:road-north"
    assert state["current_location_id"] == "location:old-mill"
    assert state["destination_id"] == "location:old-mill"

    state = advance_travel_state(state, "I look around near the old mill.")
    assert state["current_location_id"] == "location:old-mill"
    assert state["direction"] == "around"

    state = advance_travel_state(state, "I head back south toward the tavern.")
    assert state["previous_location_id"] == "location:old-mill"
    assert state["current_location_id"] == "location:tavern"
    assert state["destination_id"] == "location:tavern"
    assert state["direction"] == "south"


def test_phase13_60_travel_state_appends_new_location_beyond_initial_seed():
    state = initial_travel_state()
    state = advance_travel_state(state, "I continue toward the old mill.")
    state = advance_travel_state(state, "I keep following the old road east toward the river town.")

    assert state["current_location_id"] == "location:river-town"
    assert state["destination_name"] == "river town"
    assert state["direction"] == "east"
    assert "location:river-town" in state["known_route"]
    assert state["travel_history"][-1]["map_expanded"] is True
    assert state["campaign_map_state"]["expansions"][-1]["to_location_id"] == "location:river-town"


def test_phase13_60_matrix_cleanup_attaches_travel_state_and_metadata():
    result = {
        "results": [
            {
                "scenario": _Scenario(),
                "result": {
                    "turns": [
                        _turn_summary(),
                        _turn_summary(),
                        _turn_summary(),
                        _turn_summary(),
                    ]
                },
            }
        ]
    }

    cleanup = apply_travel_state_to_matrix_result(result)

    assert cleanup["patch"] == TRAVEL_STATE_PATCH
    assert cleanup["changed_turns"] == 4
    turns = result["results"][0]["result"]["turns"]
    assert turns[0]["interactive_cli_travel_state"]["current_location_id"] == "location:road-north"
    assert turns[1]["interactive_cli_travel_state"]["current_location_id"] == "location:old-mill"
    assert turns[2]["interactive_cli_travel_state"]["current_location_id"] == "location:old-mill"
    assert turns[3]["interactive_cli_travel_state"]["current_location_id"] == "location:tavern"
    final = turns[3]["interactive_cli_intent_diagnostics"]["final_classification"]
    assert final["action_type"] == "travel"
    assert final["current_location_id"] == "location:tavern"
    assert final["direction"] == "south"
    assert "tavern" in final["requested_terms"]
    assert turns[3]["interactive_cli_travel_state"]["campaign_map_state"]["seed_scope"] == "local_region_seed"
