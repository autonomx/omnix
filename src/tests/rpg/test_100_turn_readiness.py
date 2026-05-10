from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary


def test_100_turn_readiness_fails_single_completed_arc_with_too_much_idle():
    transcript = [
        {
            "player_action": f"graph action {i}",
            "player_agent_selection_source": "scenario_progression_graph",
            "scenario_progression_summary": {"changed": True, "matched_node_ids": [f"node:{i}"]},
        }
        for i in range(1, 19)
    ]
    transcript.extend(
        {
            "player_action": "I regroup with Garran and review what we learned from the ambush before choosing the next lead.",
            "player_agent_selection_source": "scenario_progression_arc_complete_bridge",
            "scenario_progression_summary": {"changed": False},
        }
        for _ in range(82)
    )

    summary = {
        "quality_gate_summary": {"ok": True},
        "behavioral_autoplay_eval_summary": {
            "ok": True,
            "metrics": {
                "progression_changed_count": 18,
                "unique_progression_node_count": 18,
            },
        },
        "scenario_progression_arc_summary": {
            "arc_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 18,
            "active_graph_quest_count": 0,
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["ok"] is False
    assert result["gates"]["multi_arc_continuation_ok"] is False
    assert result["gates"]["arc_complete_idle_not_excessive_ok"] is False


def test_20_turn_readiness_accepts_completed_single_arc():
    transcript = [
        {
            "player_action": f"graph action {i}",
            "player_agent_selection_source": "scenario_progression_graph",
            "scenario_progression_summary": {"changed": True, "matched_node_ids": [f"node:{i}"]},
        }
        for i in range(1, 19)
    ]
    transcript.extend(
        {
            "player_action": "I regroup with Garran and review what we learned from the ambush before choosing the next lead.",
            "player_agent_selection_source": "scenario_progression_arc_complete_bridge",
            "scenario_progression_summary": {"changed": False},
        }
        for _ in range(2)
    )

    summary = {
        "quality_gate_summary": {"ok": True},
        "behavioral_autoplay_eval_summary": {
            "ok": True,
            "metrics": {
                "progression_changed_count": 18,
                "unique_progression_node_count": 18,
            },
        },
        "scenario_progression_arc_summary": {
            "arc_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 18,
            "active_graph_quest_count": 0,
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=20,
    )

    assert result["ok"] is True


def test_100_turn_readiness_accepts_two_completed_graphs_with_enough_progress():
    transcript = [
        {
            "player_action": f"graph action {i}",
            "player_agent_selection_source": "scenario_progression_graph",
            "scenario_progression_summary": {"changed": True, "matched_node_ids": [f"node:{i}"]},
        }
        for i in range(1, 32)
    ]
    transcript.extend(
        {
            "player_action": "I ask what lead we should follow next.",
            "player_agent_selection_source": "scenario_progression_arc_complete_bridge",
            "scenario_progression_summary": {"changed": False},
        }
        for _ in range(6)
    )

    summary = {
        "quality_gate_summary": {"ok": True},
        "behavioral_autoplay_eval_summary": {
            "ok": True,
            "metrics": {
                "progression_changed_count": 31,
                "unique_progression_node_count": 31,
            },
        },
        "scenario_progression_arc_summary": {
            "arc_complete": True,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 31,
            "active_graph_quest_count": 0,
            "graph_count": 2,
            "completed_graph_count": 2,
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["gates"]["multi_arc_continuation_ok"] is True
    assert result["gates"]["multi_graph_progression_ok"] is True