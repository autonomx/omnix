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


def test_phase13_60_travel_state_advances_round_trip_locations():
    state = initial_travel_state()

    state = advance_travel_state(state, "I leave the tavern and take the road north.")
    assert state["previous_location_id"] == "location:tavern"
    assert state["current_location_id"] == "location:road-north"
    assert state["destination_id"] == "location:road-north"
    assert state["direction"] == "north"

    state = advance_travel_state(state, "I continue toward the old mill.")
    assert state["previous_location_id"] == "location:road-north"
    assert state["current_location_id"] == "location:old-mill"
    assert state["destination_id"] == "location:old-mill"

    state = advance_travel_state(state, "I look around near the old mill.")
    assert state["current_location_id"] == "location:old-mill"
    assert state["direction"] == "north"

    state = advance_travel_state(state, "I head back south toward the tavern.")
    assert state["previous_location_id"] == "location:old-mill"
    assert state["current_location_id"] == "location:tavern"
    assert state["destination_id"] == "location:tavern"
    assert state["direction"] == "south"


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
