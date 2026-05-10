from types import SimpleNamespace


def test_graph_action_source_state_prefers_state_with_actions():
    from tests.rpg.autoplay_llm_campaign import (
        _graph_action_source_state,
        _top_scenario_progression_action,
    )

    authoritative_state = {}
    runtime_state = {
        "scenario_progression_actions": [
            {
                "action_id": "ask_bran_who_left_side_door",
                "command": "I ask Bran who left through the side door and why they were afraid.",
                "priority": 95,
            }
        ]
    }

    selected = _graph_action_source_state(authoritative_state, runtime_state)

    assert _top_scenario_progression_action(selected)["action_id"] == "ask_bran_who_left_side_door"


def test_graph_action_override_replaces_stale_road_action():
    from tests.rpg.autoplay_llm_campaign import _apply_graph_action_selection_override

    graph_state = {
        "scenario_progression_actions": [
            {
                "action_id": "ask_bran_who_left_side_door",
                "command": "I ask Bran who left through the side door and why they were afraid.",
                "priority": 95,
            }
        ]
    }
    args = SimpleNamespace(
        strategy="goal_directed_quest_runner",
        autoplay_profile="",
        player_agent_goal_pressure_repair=True,
    )

    action, source, reason, debug = _apply_graph_action_selection_override(
        player_action="I inspect the road outside the tavern for fresh tracks.",
        player_agent_selection_source="llm_player_agent",
        player_agent_selection_reason="llm",
        player_agent_debug={},
        graph_state=graph_state,
        args=args,
    )

    assert action == "I ask Bran who left through the side door and why they were afraid."
    assert source == "scenario_progression_graph"
    assert reason == "scenario_progression_graph_action_preferred_over_llm"
    assert debug["scenario_progression_graph_action_preferred"]["action_id"] == "ask_bran_who_left_side_door"


def test_recent_same_graph_action_without_progress_detects_stall():
    from tests.rpg.autoplay_llm_campaign import (
        _recent_same_graph_action_without_progress,
    )

    transcript = [
        {
            "player_action": "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
            "top_scenario_progression_action_id": "scout_quarry_road",
            "scenario_progression_summary": {"changed": False},
        },
        {
            "player_action": "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
            "top_scenario_progression_action_id": "scout_quarry_road",
            "scenario_progression_summary": {"changed": False},
        },
    ]

    assert _recent_same_graph_action_without_progress(
        transcript,
        action_id="scout_quarry_road",
        command="I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        max_repeats=2,
    )