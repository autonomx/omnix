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
            "graph_count": 1,
            "completed_graph_count": 1,
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["ok"] is False
    assert result["gates"]["multi_arc_continuation_ok"] is False
    assert result["gates"]["arc_complete_idle_not_excessive_ok"] is True  # Allowed when waiting for next graph pack


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
            "graph_count": 4,
            "completed_graph_count": 4,
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


def test_100_turn_readiness_classifies_two_graph_content_exhaustion():
    transcript = [
        {
            "turn": i,
            "player_action": f"graph action {i}",
            "top_scenario_progression_action_id": f"node_{i}",
            "scenario_progression_summary": {"changed": True},
        }
        for i in range(1, 28)
    ]
    transcript.extend(
        {
            "turn": i,
            "player_action": "I regroup with Garran and review the completed ambush and mill investigation before choosing the next lead.",
            "top_scenario_progression_action_id": "arc_complete_regroup",
            "scenario_progression_summary": {"changed": False},
        }
        for i in range(28, 101)
    )

    summary = {
        "behavioral_autoplay_eval_summary": {
            "metrics": {
                "progression_changed_count": 27,
                "unique_progression_node_count": 27,
            }
        },
        "scenario_progression_arc_summary": {
            "graph_count": 2,
            "completed_graph_count": 2,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 27,
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["ok"] is False
    assert result["classification"] == "content_exhausted_waiting_for_next_graph_pack"
    assert result["gates"]["graph_packs_completed_ok"] is True
    assert result["gates"]["needs_more_graph_content_ok"] is False


def test_100_turn_readiness_uses_campaign_complete_arc_summary():
    from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary

    transcript = [
        {
            "turn_index": i,
            "player_action": f"graph action {i}",
            "top_scenario_progression_action_id": f"node_{i}",
            "scenario_progression_summary": {"changed": True},
        }
        for i in range(1, 28)
    ]
    transcript.extend(
        {
            "turn_index": i,
            "player_action": "I regroup with Garran and review the completed ambush and mill investigation before choosing the next lead.",
            "top_scenario_progression_action_id": "arc_complete_regroup",
            "scenario_progression_summary": {"changed": False},
        }
        for i in range(28, 101)
    )

    summary = {
        "scenario_progression_arc_summary": {
            "graph_count": 2,
            "completed_graph_count": 2,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 27,
        },
        "behavioral_autoplay_eval_summary": {
            "metrics": {
                "progression_changed_count": 27,
                "unique_progression_node_count": 27,
            }
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["classification"] == "content_exhausted_waiting_for_next_graph_pack"
    assert result["graph_count"] == 2
    assert result["completed_graph_count"] == 2
    assert result["campaign_graphs_complete"] is True
    assert result["waiting_for_next_graph_pack"] is True


def test_100_turn_readiness_passes_density_with_three_graphs_but_still_needs_next_content():
    transcript = [
        {
            "turn_index": i,
            "player_action": f"graph action {i}",
            "top_scenario_progression_action_id": f"node_{i}",
            "scenario_progression_summary": {"changed": True},
        }
        for i in range(1, 38)
    ]
    transcript.extend(
        {
            "turn_index": i,
            "player_action": "I regroup with Garran and review the completed ambush, mill, and shrine investigation before choosing the next lead.",
            "top_scenario_progression_action_id": "arc_complete_regroup",
            "scenario_progression_summary": {"changed": False},
        }
        for i in range(38, 101)
    )

    summary = {
        "scenario_progression_arc_summary": {
            "graph_count": 3,
            "completed_graph_count": 3,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 37,
        },
        "behavioral_autoplay_eval_summary": {
            "metrics": {
                "progression_changed_count": 37,
                "unique_progression_node_count": 37,
            }
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["gates"]["graph_progression_density_ok"] is True
    assert result["gates"]["unique_progression_nodes_ok"] is True
    assert result["gates"]["needs_more_graph_content_ok"] is False
    assert result["classification"] == "content_exhausted_waiting_for_next_graph_pack"


def test_100_turn_readiness_with_four_graphs_only_fails_next_content_gate():
    transcript = [
        {
            "turn_index": i,
            "player_action": f"graph action {i}",
            "top_scenario_progression_action_id": f"node_{i}",
            "scenario_progression_summary": {"changed": True},
        }
        for i in range(1, 50)
    ]
    transcript.extend(
        {
            "turn_index": i,
            "player_action": "I regroup with Bran and Garran after exposing Captain Voss, then consider which faction backed him.",
            "top_scenario_progression_action_id": "arc_complete_regroup",
            "scenario_progression_summary": {"changed": False},
        }
        for i in range(50, 101)
    )

    summary = {
        "scenario_progression_arc_summary": {
            "graph_count": 4,
            "completed_graph_count": 4,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 49,
        },
        "behavioral_autoplay_eval_summary": {
            "metrics": {
                "progression_changed_count": 49,
                "unique_progression_node_count": 49,
            }
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["gates"]["graph_progression_density_ok"] is True
    assert result["gates"]["unique_progression_nodes_ok"] is True
    assert result["gates"]["arc_complete_idle_not_excessive_ok"] is True
    assert result["failed_gates"] == ["needs_more_graph_content_ok"]


def test_100_turn_readiness_with_five_graphs_only_fails_next_content_gate():
    from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary

    transcript = [
        {
            "turn_index": i,
            "player_action": f"graph action {i}",
            "top_scenario_progression_action_id": f"node_{i}",
            "scenario_progression_summary": {"changed": True},
        }
        for i in range(1, 62)
    ]
    transcript.extend(
        {
            "turn_index": i,
            "player_action": "I regroup with Bran and Garran after exposing the Sable Chain connection, then plan how to move against the faction behind Captain Voss.",
            "top_scenario_progression_action_id": "arc_complete_regroup",
            "scenario_progression_summary": {"changed": False},
        }
        for i in range(62, 101)
    )

    summary = {
        "scenario_progression_arc_summary": {
            "graph_count": 5,
            "completed_graph_count": 5,
            "campaign_graphs_complete": True,
            "waiting_for_next_graph_pack": True,
            "completed_node_count": 61,
        },
        "behavioral_autoplay_eval_summary": {
            "metrics": {
                "progression_changed_count": 61,
                "unique_progression_node_count": 61,
            }
        },
    }

    result = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=transcript,
        requested_turns=100,
    )

    assert result["gates"]["graph_progression_density_ok"] is True
    assert result["gates"]["unique_progression_nodes_ok"] is True
    assert result["gates"]["arc_complete_idle_not_excessive_ok"] is True
    assert result["failed_gates"] == ["needs_more_graph_content_ok"]