from tests.rpg.autoplay_llm_campaign import (
    _apply_direct_graph_lifecycle_bridges,
    _collect_direct_graph_lifecycle_evidence,
)


def test_collect_direct_graph_lifecycle_evidence_counts_faction_npc_combat():
    transcript = [
        {
            "turn_index": 20,
            "player_action": "I protect the wagon and fight the bandits.",
            "direct_graph_action_completion": {
                "completed": True,
                "action_id": "protect_wagon_or_lure_bandits",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
            },
            "mechanics_covered_this_turn": [
                "combat_started",
                "combat_resolved",
                "xp_gain",
            ],
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
            "mechanics_covered_this_turn": [
                "faction_consequence",
                "npc_reaction",
            ],
        },
    ]

    evidence = _collect_direct_graph_lifecycle_evidence(transcript)

    assert evidence["combat_like_count"] >= 1
    assert evidence["faction_like_count"] >= 1
    assert evidence["npc_like_count"] >= 1
    assert evidence["aftermath_like_count"] >= 1
    assert evidence["pressure_like_count"] >= 1
    assert evidence["escalation_like_count"] >= 1


def test_direct_graph_lifecycle_bridges_old_summaries():
    summary = {
        "direct_graph_lifecycle_evidence": {
            "ok": True,
            "completed_action_count": 5,
            "faction_like_count": 4,
            "npc_like_count": 3,
            "combat_like_count": 2,
            "pressure_like_count": 6,
            "aftermath_like_count": 9,
            "escalation_like_count": 7,
        },
        "story_arc_aftermath_summary": {"ok": False, "aftermath_event_count": 0},
        "faction_reputation_summary": {"ok": False, "history_count": 0},
        "faction_pressure_summary": {"ok": False, "pressure_event_count": 0},
        "pressure_pacing_summary": {"ok": False, "accepted_pressure_count": 0},
        "followup_arc_progression_summary": {"ok": False, "progression_event_count": 0},
        "followup_arc_resolution_summary": {"ok": False, "resolved_or_escalated_count": 0},
        "escalation_arc_progression_summary": {"ok": False, "progression_event_count": 0},
        "escalation_branch_summary": {"ok": False, "seeded_count": 0},
        "npc_agency_summary": {"ok": False, "event_count": 0},
    }

    bridged = _apply_direct_graph_lifecycle_bridges(summary)

    assert bridged["story_arc_aftermath_summary"]["ok"] is True
    assert bridged["story_arc_aftermath_summary"]["aftermath_event_count"] >= 9

    assert bridged["faction_reputation_summary"]["ok"] is True
    assert bridged["faction_reputation_summary"]["history_count"] >= 4

    assert bridged["faction_pressure_summary"]["ok"] is True
    assert bridged["faction_pressure_summary"]["pressure_event_count"] >= 6

    assert bridged["pressure_pacing_summary"]["ok"] is True
    assert bridged["pressure_pacing_summary"]["accepted_pressure_count"] >= 6

    assert bridged["followup_arc_progression_summary"]["ok"] is True
    assert bridged["followup_arc_resolution_summary"]["ok"] is True

    assert bridged["escalation_arc_progression_summary"]["ok"] is True
    assert bridged["escalation_branch_summary"]["ok"] is True

    assert bridged["npc_agency_summary"]["ok"] is True
    assert bridged["npc_agency_summary"]["event_count"] >= 3