from tests.rpg.autoplay_llm_campaign import (
    _filtered_graph_action_state_for_selection,
    _graph_expected_action_is_available,
    _top_scenario_progression_action,
)


def test_suppressed_expected_graph_action_is_not_available():
    raw_state = {
        "scenario_progression_actions": [
            {
                "action_id": "ask_garran_to_join",
                "command": "I ask Garran to join me on the mill road.",
                "mechanic": "party_setup",
                "action_terms": ["ask garran", "join me", "mill road"],
            },
            {
                "action_id": "buy_rations_from_bran",
                "command": "I buy two rations from Bran.",
                "mechanic": "buying",
                "action_terms": ["buy", "rations", "bran"],
            },
        ]
    }

    filtered = _filtered_graph_action_state_for_selection(
        raw_state,
        suppressed_actions={
            "ask_garran_to_join": {
                "action_id": "ask_garran_to_join",
                "suppressed_turn": 10,
                "cooldown_turns": 12,
            }
        },
        completed_action_ids=set(),
        completed_mechanics=set(),
        turn_index=15,
    )

    top = _top_scenario_progression_action(filtered)

    assert top["action_id"] == "buy_rations_from_bran"

    suppressed_action = raw_state["scenario_progression_actions"][0]
    assert _graph_expected_action_is_available(
        suppressed_action,
        suppressed_actions={
            "ask_garran_to_join": {
                "action_id": "ask_garran_to_join",
                "suppressed_turn": 10,
                "cooldown_turns": 12,
            }
        },
        completed_action_ids=set(),
        completed_mechanics=set(),
        turn_index=15,
    ) is False