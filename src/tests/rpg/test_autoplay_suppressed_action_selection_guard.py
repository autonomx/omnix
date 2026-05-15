from tests.rpg.autoplay_llm_campaign import (
    _guard_suppressed_selected_action,
)


def test_suppressed_selected_action_retargets_to_unsuppressed_action():
    actions = [
        {
            "id": "ask_garran_to_join",
            "command": "I ask Garran to join me on the mill road.",
            "mechanic": "party_setup",
            "action_terms": ["ask garran", "join me", "mill road"],
        },
        {
            "id": "buy_rations_from_bran",
            "command": "I buy two rations from Bran.",
            "mechanic": "buying",
            "action_terms": ["buy", "rations", "bran"],
        },
    ]

    guard = _guard_suppressed_selected_action(
        selected_command="I ask Garran to join me on the mill road.",
        all_graph_actions=actions,
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
    assert guard["replacement_action"]["id"] == "buy_rations_from_bran"


def test_suppressed_selected_action_noops_when_not_suppressed():
    actions = [
        {
            "id": "ask_garran_to_join",
            "command": "I ask Garran to join me on the mill road.",
            "mechanic": "party_setup",
            "action_terms": ["ask garran", "join me", "mill road"],
        }
    ]

    guard = _guard_suppressed_selected_action(
        selected_command="I ask Garran to join me on the mill road.",
        all_graph_actions=actions,
        suppressed_actions={},
        completed_action_ids=set(),
        completed_mechanics=set(),
        turn_index=15,
    )

    assert guard["retargeted"] is False
    assert guard["command"] == "I ask Garran to join me on the mill road."