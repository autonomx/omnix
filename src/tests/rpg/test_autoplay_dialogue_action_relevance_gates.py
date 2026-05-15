from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
    _build_dialogue_action_relevance_summary,
)


def test_dialogue_relevance_summary_counts_repaired_mismatch():
    summary = _build_dialogue_action_relevance_summary(
        transcript=[
            {
                "turn_index": 1,
                "player_action": "I buy two rations from Bran.",
                "dialogue_source": "deterministic_action_relevance_fallback",
                "dialogue_action_relevance": {
                    "ok": False,
                    "action_kind": "commerce",
                    "dialogue_kind": "social_investigation",
                    "reasons": ["commerce_action_dialogue_mismatch"],
                },
                "dialogue_display_source_gate": {
                    "ok": False,
                    "blocked_reasons": ["commerce_blocks_witness_hook_display"],
                },
                "dialogue_action_relevance_repaired": True,
                "dialogue_action_relevance_after_repair": {
                    "ok": True,
                    "action_kind": "commerce",
                    "dialogue_kind": "general",
                    "reasons": [],
                },
            }
        ]
    )

    assert summary["checked_count"] == 1
    assert summary["mismatch_count"] == 1
    assert summary["repaired_count"] == 1
    assert summary["unrepaired_count"] == 0
    assert summary["ok"] is True


def test_evaluation_dialogue_action_relevance_gate_passes():
    evaluation = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"turn_index": i + 1} for i in range(100)],
        performance_summary={"avg_turn_seconds": 1, "p95_turn_seconds": 2, "max_turn_seconds": 3},
        narration_grounding_summary={"checked_count": 100},
        progress_quality_summary={"meaningful_progress_rate": 1.0},
        checkpoint_summary={"checkpoint_validation_failures": 0},
        loop_detection_summary={"loop_warning_count": 0},
        mechanics_coverage_summary={"required_ok": True, "real_required_ok": True},
        dialogue_action_relevance_summary={
            "ok": True,
            "checked_count": 100,
            "mismatch_count": 12,
            "mismatch_rate": 0.12,
            "repaired_count": 12,
            "unrepaired_count": 0,
            "source_gate_block_count": 8,
            "by_reason": {"commerce_action_dialogue_mismatch": 4},
        },
    )

    assert evaluation["gates"]["dialogue_action_relevance_ok"]["ok"] is True


def test_readiness_dialogue_action_relevance_gate_passes():
    readiness = _build_100_turn_readiness_summary(
        summary={
            "dialogue_action_relevance_summary": {
                "ok": True,
                "checked_count": 100,
                "mismatch_count": 12,
                "mismatch_rate": 0.12,
                "repaired_count": 12,
                "unrepaired_count": 0,
                "source_gate_block_count": 8,
                "by_reason": {"commerce_action_dialogue_mismatch": 4},
            }
        },
        transcript=[],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["dialogue_action_relevance_ok"]["ok"] is True