from __future__ import annotations

from app.rpg.presentation.dialogue_quality_benchmark import (
    build_provider_free_dialogue_matrix,
    evaluate_dialogue_quality_matrix,
)


def test_expanded_dialogue_quality_matrix_meets_release_thresholds() -> None:
    cases = build_provider_free_dialogue_matrix()
    report = evaluate_dialogue_quality_matrix(cases)

    assert len(cases) >= 35
    assert report["accepted_case_count"] >= 30
    assert report["rejected_case_count"] >= 5
    assert report["ok"] is True, report
    assert report["failures"] == []
    assert report["metrics"] == {
        "direct_answer_rate": 1.0,
        "correct_speaker_rate": 1.0,
        "grounded_specificity_rate": 1.0,
        "continuity_rate": 1.0,
        "near_duplicate_rate": 0.0,
        "private_leak_rate": 0.0,
        "empty_line_rate": 0.0,
        "candidate_rejection_rate": 1.0,
    }


def test_matrix_covers_original_missing_dialogue_categories() -> None:
    report = evaluate_dialogue_quality_matrix(build_provider_free_dialogue_matrix())
    categories = set(report["categories"])

    assert {
        "emotional_disclosure",
        "hostile_noncombat",
        "private_secret_probe",
        "absent_npc",
        "group_conversation",
        "low_trust",
        "high_trust",
        "follow_up_reference",
        "multi_turn_repetition",
    } <= categories


def test_bad_candidates_are_rejected_for_the_expected_reasons() -> None:
    report = evaluate_dialogue_quality_matrix(build_provider_free_dialogue_matrix())
    rejected = {
        row["case_id"]: row
        for row in report["cases"]
        if row["should_accept"] is False
    }

    assert "speaker_mismatch" in rejected["reject:wrong-speaker"]["violations"]
    assert "player_input_restatement" in rejected["reject:restatement"]["violations"]
    assert "private_profile_leak" in rejected["reject:private-leak"]["violations"]
    assert "missing_npc_line" in rejected["reject:empty-line"]["violations"]
    assert "near_duplicate_recent_response" in rejected["reject:near-duplicate"]["violations"]
