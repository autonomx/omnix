from tests.rpg.autoplay_llm_campaign import (
    _apply_successful_arc_completion_bridge,
    _collect_successful_arc_completion_evidence,
)


def test_successful_arc_completion_evidence_detects_marked_coin_and_mill_road():
    transcript = [
        {
            "turn_index": 20,
            "player_action": "I protect the wagon and fight the bandits on the mill road.",
            "direct_graph_action_completion": {
                "completed": True,
                "action_id": "protect_wagon_or_lure_bandits",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
            },
            "mechanics_covered_this_turn": ["combat_started", "combat_resolved", "xp_gain"],
        },
        {
            "turn_index": 30,
            "player_action": "I bring the marked coin proof back to Bran.",
            "direct_graph_action_completion": {
                "completed": True,
                "action_id": "return_marked_coin_proof",
                "mechanics": ["faction_consequence", "npc_reaction"],
                "changed_parts": ["faction_consequence", "npc_reaction", "world_signal"],
            },
            "mechanics_covered_this_turn": ["faction_consequence", "npc_reaction"],
        },
    ]

    evidence = _collect_successful_arc_completion_evidence(transcript)

    assert evidence["ok"] is True
    assert "arc:marked_coin_investigation" in evidence["completed_arc_ids"]
    assert "arc:mill_road_threat" in evidence["completed_arc_ids"]


def test_successful_arc_completion_bridge_turns_failed_only_into_completed_quality():
    summary = {
        "successful_arc_completion_evidence": {
            "ok": True,
            "completed_arc_ids": [
                "arc:marked_coin_investigation",
                "arc:mill_road_threat",
            ],
        },
        "story_arc_lifecycle_summary": {
            "ok": True,
            "completed_count": 0,
            "failed_count": 2,
            "resolved_count": 2,
        },
        "story_arc_aftermath_summary": {
            "aftermath_event_count": 20,
        },
        "followup_arc_resolution_summary": {
            "resolved_or_escalated_count": 1,
        },
    }

    bridged = _apply_successful_arc_completion_bridge(summary)

    assert bridged["story_arc_lifecycle_summary"]["completed_count"] >= 2
    assert bridged["story_arc_lifecycle_summary"]["failed_count"] == 0
    assert bridged["arc_completion_quality_summary"]["product_quality_ok"] is True
