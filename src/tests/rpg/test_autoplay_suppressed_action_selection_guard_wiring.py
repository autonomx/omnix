from tests.rpg.autoplay_llm_campaign import (
    _filtered_graph_action_state_for_selection,
    _guard_suppressed_selected_action,
    _top_scenario_progression_action,
)


def test_filtered_graph_state_removes_suppressed_top_action():
    raw_state = {
        "scenario_progression_actions": [
            {
                "action_id": "ask_garran_to_join",
                "command": "I ask Garran to join me on the mill road.",
                "mechanic": "party_setup",
                "priority": 100,
                "action_terms": ["ask garran", "join me", "mill road"],
            },
            {
                "action_id": "buy_rations_from_bran",
                "command": "I buy two rations from Bran.",
                "mechanic": "buying",
                "priority": 90,
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
    assert len(filtered["scenario_progression_actions_all"]) == 2
    assert len(filtered["scenario_progression_actions"]) == 1


def test_guard_retargets_suppressed_selected_command_using_all_actions():
    all_actions = [
        {
            "action_id": "ask_garran_to_join",
            "command": "I ask Garran to join me on the mill road.",
            "mechanic": "party_setup",
            "priority": 100,
            "action_terms": ["ask garran", "join me", "mill road"],
        },
        {
            "action_id": "buy_rations_from_bran",
            "command": "I buy two rations from Bran.",
            "mechanic": "buying",
            "priority": 90,
            "action_terms": ["buy", "rations", "bran"],
        },
    ]

    guard = _guard_suppressed_selected_action(
        selected_command="I ask Garran to join me on the mill road.",
        all_graph_actions=all_actions,
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

    assert guard["retargeted"] is True
    assert guard["command"] == "I buy two rations from Bran."