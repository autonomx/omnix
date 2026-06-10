from app.rpg.interactive_cli_response_quality import (
    apply_interactive_response_quality_cleanup,
    apply_response_quality_to_matrix_result,
)


class _Scenario:
    scenario_id = "travel_round_trip_route"
    commands = (
        "I leave the tavern and take the road north.",
        "I continue toward the old mill.",
        "I look around near the old mill.",
        "I head back south toward the tavern.",
    )


def _travel_turn_summary(*, player_input="", action_type="general", requested_terms=None, narration=None):
    raw_narration = narration or "The moment responds without producing a major new consequence."
    diagnostics = {
        "final_classification": {
            "action_type": action_type,
            "target_npc": "",
            "requested_terms": list(requested_terms or []),
        }
    }
    return {
        "player_input": player_input,
        "raw_result": {
            "narration": raw_narration,
            "npc": {"speaker": "", "line": ""},
            "interactive_cli_intent_diagnostics": diagnostics,
        },
        "raw_narration": raw_narration,
        "narration_preview": raw_narration,
        "interactive_cli_intent_diagnostics": diagnostics,
        "extracted": {},
    }


def _final_classification(turn):
    return turn["interactive_cli_intent_diagnostics"]["final_classification"]


def test_phase13_54_travel_round_trip_generic_movement_gets_route_specific_text_and_metadata():
    repaired = apply_interactive_response_quality_cleanup(
        _travel_turn_summary(
            player_input="I leave the tavern and take the road north.",
            action_type="general",
            requested_terms=["leave", "tavern", "road", "north"],
            narration="The scene shifts with the movement.",
        ),
        player_input="I leave the tavern and take the road north.",
    )

    assert repaired["interactive_cli_response_quality"]["cleanup_source"] == "travel_round_trip_specificity"
    assert "road" in repaired["raw_narration"].lower()
    assert "tavern" in repaired["raw_narration"].lower()
    assert "north" in repaired["raw_narration"].lower()
    assert _final_classification(repaired)["action_type"] == "travel"
    assert "road" in _final_classification(repaired)["requested_terms"]
    assert "north" in _final_classification(repaired)["requested_terms"]


def test_phase13_54_travel_round_trip_old_mill_lookaround_gets_location_text():
    repaired = apply_interactive_response_quality_cleanup(
        _travel_turn_summary(
            player_input="I look around near the old mill.",
            action_type="exploration",
            requested_terms=["look", "old mill"],
        ),
        player_input="I look around near the old mill.",
    )

    assert "old mill" in repaired["raw_narration"].lower()
    assert "look around" in repaired["raw_narration"].lower()
    assert "road" in repaired["raw_narration"].lower()
    assert _final_classification(repaired)["action_type"] == "travel"
    assert "old mill" in _final_classification(repaired)["requested_terms"]


def test_phase13_54_matrix_cleanup_uses_scenario_commands_and_updates_travel_metadata():
    result = {
        "results": [
            {
                "scenario": _Scenario(),
                "result": {
                    "turns": [
                        _travel_turn_summary(player_input="", action_type="general", narration="The scene shifts with the movement."),
                        _travel_turn_summary(player_input="", action_type="general"),
                        _travel_turn_summary(player_input="", action_type="general"),
                        _travel_turn_summary(player_input="", action_type="general"),
                    ]
                },
            }
        ]
    }

    cleanup = apply_response_quality_to_matrix_result(result)

    assert cleanup["changed_turns"] == 4
    turns = result["results"][0]["result"]["turns"]
    assert turns[0]["interactive_cli_intent_diagnostics"]["final_classification"]["action_type"] == "travel"
    assert "road" in turns[0]["raw_narration"].lower()
    assert "old mill" in turns[1]["raw_narration"].lower()
    assert "old mill" in turns[2]["raw_narration"].lower()
    assert "south" in turns[3]["raw_narration"].lower()
    assert "tavern" in turns[3]["raw_narration"].lower()
