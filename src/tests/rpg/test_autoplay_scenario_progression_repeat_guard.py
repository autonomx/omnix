from tests.rpg.autoplay_llm_campaign import (
    _build_scenario_progression_action_repeat_summary,
    _filter_suppressed_graph_actions,
)


def test_filter_suppressed_graph_actions_removes_suppressed_action():
    actions = [
        {"id": "ask_garran_to_join", "command": "I ask Garran to join me."},
        {"id": "buy_rations", "command": "I buy two rations from Bran."},
    ]

    filtered = _filter_suppressed_graph_actions(
        actions,
        suppressed_actions={
            "ask_garran_to_join": {
                "action_id": "ask_garran_to_join",
                "suppressed_turn": 10,
                "cooldown_turns": 12,
                "reason": "repeated_without_progress",
            }
        },
        completed_action_ids=set(),
        completed_mechanics=set(),
        turn_index=15,
    )

    assert [row["id"] for row in filtered] == ["buy_rations"]


def test_filter_suppressed_graph_actions_removes_completed_mechanic():
    actions = [
        {
            "id": "ask_garran_to_join",
            "mechanic": "party_setup",
            "command": "I ask Garran to join me.",
        },
        {
            "id": "buy_rations",
            "mechanic": "buying",
            "command": "I buy two rations from Bran.",
        },
    ]

    filtered = _filter_suppressed_graph_actions(
        actions,
        suppressed_actions={},
        completed_action_ids=set(),
        completed_mechanics={"party_setup"},
        turn_index=20,
    )

    assert [row["id"] for row in filtered] == ["buy_rations"]


def test_filter_suppressed_graph_actions_allows_after_cooldown():
    actions = [
        {"id": "ask_garran_to_join", "command": "I ask Garran to join me."},
    ]

    filtered = _filter_suppressed_graph_actions(
        actions,
        suppressed_actions={
            "ask_garran_to_join": {
                "action_id": "ask_garran_to_join",
                "suppressed_turn": 10,
                "cooldown_turns": 12,
                "reason": "repeated_without_progress",
            }
        },
        completed_action_ids=set(),
        completed_mechanics=set(),
        turn_index=25,
    )

    assert [row["id"] for row in filtered] == ["ask_garran_to_join"]


def test_scenario_progression_repeat_summary_bounds_warnings():
    summary = _build_scenario_progression_action_repeat_summary(
        warnings=[
            {
                "type": "scenario_progression_graph_action_repeated_without_progress",
                "turn": 15,
                "action_id": "ask_garran_to_join",
            }
        ],
        suppressed_actions={
            "ask_garran_to_join": {
                "action_id": "ask_garran_to_join",
                "suppressed_turn": 15,
            }
        },
    )

    assert summary["ok"] is True
    assert summary["repeat_warning_count"] == 1
    assert summary["suppressed_action_count"] == 1