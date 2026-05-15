from argparse import Namespace

from tests.rpg.autoplay_llm_campaign import (
    _apply_direct_graph_lifecycle_bridges,
    _rebuild_final_100_turn_evaluation,
)


def test_direct_bridge_survives_legacy_summary_overwrite():
    summary = {
        "requested_turns": 100,
        "turns_executed": 100,
        "runtime_errors": [],
        "warnings": [],
        "performance_seconds_summary": {
            "avg_turn_seconds": 1.0,
            "p95_turn_seconds": 2.0,
            "max_turn_seconds": 3.0,
        },
        "narration_grounding_summary": {"checked_count": 100},
        "canonical_progress_quality": {"meaningful_progress_rate": 1.0},
        "checkpoint_summary": {"checkpoint_validation_failures": 0},
        "loop_detection_summary": {"loop_warning_count": 0},
        "mechanics_coverage_summary": {
            "required_ok": True,
            "real_required_ok": True,
        },
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

        # Simulate legacy summary builders overwriting bridged values to zero.
        "story_arc_aftermath_summary": {"ok": False, "aftermath_event_count": 0},
        "faction_reputation_summary": {"ok": False, "history_count": 0},
        "faction_pressure_summary": {"ok": False, "pressure_event_count": 0},
        "pressure_pacing_summary": {"ok": False, "accepted_pressure_count": 0},
        "followup_arc_progression_summary": {"ok": False, "progression_event_count": 0},
        "followup_arc_resolution_summary": {"ok": False, "resolved_or_escalated_count": 0},
        "escalation_branch_summary": {"ok": False, "seeded_count": 0},
        "escalation_arc_progression_summary": {"ok": False, "progression_event_count": 0},
        "npc_agency_summary": {"ok": False, "event_count": 0},
    }

    bridged = _apply_direct_graph_lifecycle_bridges(summary)

    assert bridged["story_arc_aftermath_summary"]["aftermath_event_count"] >= 9
    assert bridged["faction_reputation_summary"]["history_count"] >= 4
    assert bridged["faction_pressure_summary"]["pressure_event_count"] >= 6
    assert bridged["pressure_pacing_summary"]["accepted_pressure_count"] >= 6
    assert bridged["followup_arc_progression_summary"]["progression_event_count"] >= 1
    assert bridged["followup_arc_resolution_summary"]["resolved_or_escalated_count"] >= 1
    assert bridged["escalation_branch_summary"]["seeded_count"] >= 1
    assert bridged["escalation_arc_progression_summary"]["progression_event_count"] >= 1
    assert bridged["npc_agency_summary"]["event_count"] >= 3


def test_rebuild_final_evaluation_applies_direct_bridge_before_gates():
    summary = {
        "requested_turns": 100,
        "turns_executed": 100,
        "runtime_errors": [],
        "warnings": [],
        "performance_seconds_summary": {
            "avg_turn_seconds": 1.0,
            "p95_turn_seconds": 2.0,
            "max_turn_seconds": 3.0,
        },
        "narration_grounding_summary": {"checked_count": 100},
        "canonical_progress_quality": {"meaningful_progress_rate": 1.0},
        "checkpoint_summary": {"checkpoint_validation_failures": 0},
        "loop_detection_summary": {"loop_warning_count": 0},
        "mechanics_coverage_summary": {
            "required_ok": True,
            "real_required_ok": True,
        },
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
        "escalation_branch_summary": {"ok": False, "seeded_count": 0},
        "escalation_arc_progression_summary": {"ok": False, "progression_event_count": 0},
        "npc_agency_summary": {"ok": False, "event_count": 0},
    }

    rebuilt = _rebuild_final_100_turn_evaluation(
        args=Namespace(turns=100),
        summary=summary,
        transcript=[{"turn_index": i + 1} for i in range(100)],
        direct_graph_lifecycle_evidence=summary["direct_graph_lifecycle_evidence"],
    )

    gates = rebuilt["hundred_turn_evaluation"]["gates"]

    for gate_name in (
        "story_arc_aftermath_present",
        "faction_reputation_changed",
        "faction_pressure_present",
        "pressure_pacing_active",
        "followup_arc_progression_present",
        "followup_arc_resolution_present",
        "escalation_branch_seeded",
        "escalation_arc_progression_present",
        "npc_agency_present",
    ):
        assert gates[gate_name]["ok"] is True, gate_name
