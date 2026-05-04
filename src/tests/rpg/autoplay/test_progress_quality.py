from tests.rpg.autoplay.progress_quality import (
    churn_only_streak,
    classify_turn_progress_quality,
    compute_progress_quality_metrics,
    evaluate_progress_quality_health,
    objective_target_no_meaningful_progress_streak,
)


def test_classify_turn_progress_quality_meaningful():
    row = {
        "progress_delta": {"categories": ["milestone_completed"]},
        "player_action": "I find the witness.",
    }

    quality = classify_turn_progress_quality(row)

    assert quality["quality"] == "meaningful_progress"
    assert quality["meaningful"] == ["milestone_completed"]


def test_classify_turn_progress_quality_churn_only():
    row = {
        "progress_delta": {"categories": ["state_changed"]},
        "player_action": "I ask Bran again.",
    }

    quality = classify_turn_progress_quality(row)

    assert quality["quality"] == "churn_only"
    assert quality["churn_only"] == ["state_changed"]


def test_classify_turn_progress_quality_journal_only_is_weak_progress():
    row = {
        "progress_delta": {"categories": ["journal_entry_added"]},
        "player_action": "I write down what happened.",
    }

    quality = classify_turn_progress_quality(row)

    assert quality["quality"] == "weak_progress"
    assert quality["weak_progress"] == ["journal_entry_added"]
    assert quality["meaningful"] == []


def test_classify_turn_progress_quality_journal_plus_arc_is_meaningful():
    row = {
        "progress_delta": {"categories": ["journal_entry_added", "arc_stage_changed"]},
        "player_action": "I report the findings.",
    }

    quality = classify_turn_progress_quality(row)

    assert quality["quality"] == "meaningful_progress"
    assert "arc_stage_changed" in quality["meaningful"]
    assert "journal_entry_added" in quality["meaningful"]


def test_classify_turn_progress_quality_objective_targeted_from_goal_id():
    row = {
        "progress_delta": {"categories": ["state_changed"]},
        "selected_player_action": {"goal_id": "milestone:find_witness"},
        "player_action_context": {
            "active_objectives": [
                {"objective_id": "milestone:find_witness"},
            ]
        },
        "player_action": "I focus on the witness.",
    }

    quality = classify_turn_progress_quality(row)

    assert quality["objective_targeted"] is True


def test_compute_progress_quality_metrics_counts_quality():
    transcript = [
        {"progress_quality": {"quality": "meaningful_progress", "meaningful": ["journal_entry_added"]}},
        {"progress_quality": {"quality": "churn_only", "churn_only": ["state_changed"]}},
    ]

    metrics = compute_progress_quality_metrics(transcript)

    assert metrics["meaningful_turns"] == 1
    assert metrics["churn_only_turns"] == 1
    assert metrics["meaningful_progress_rate"] == 0.5


def test_churn_only_streak_counts_trailing_churn():
    transcript = [
        {"progress_quality": {"quality": "meaningful_progress"}},
        {"progress_quality": {"quality": "churn_only"}},
        {"progress_quality": {"quality": "churn_only"}},
    ]

    assert churn_only_streak(transcript) == 2


def test_objective_target_no_meaningful_progress_streak_counts_trailing_targeted_churn():
    transcript = [
        {"progress_quality": {"objective_targeted": True, "meaningful": ["journal_entry_added"]}},
        {"progress_quality": {"objective_targeted": True, "meaningful": []}},
        {"progress_quality": {"objective_targeted": True, "meaningful": []}},
    ]

    assert objective_target_no_meaningful_progress_streak(transcript) == 2


def test_evaluate_progress_quality_health_can_warn_on_low_meaningful_rate():
    transcript = [
        {"progress_quality": {"quality": "churn_only", "churn_only": ["state_changed"]}},
        {"progress_quality": {"quality": "churn_only", "churn_only": ["state_changed"]}},
    ]

    health = evaluate_progress_quality_health(
        transcript,
        min_meaningful_progress_rate=0.25,
    )

    assert health["ok"] is False
    assert "meaningful_progress_rate_below_threshold" in health["warnings"]


def test_evaluate_progress_quality_health_can_warn_on_churn_streak():
    transcript = [
        {"progress_quality": {"quality": "churn_only", "churn_only": ["state_changed"]}},
        {"progress_quality": {"quality": "churn_only", "churn_only": ["state_changed"]}},
    ]

    health = evaluate_progress_quality_health(
        transcript,
        max_churn_only_streak=1,
    )

    assert health["ok"] is False
    assert "churn_only_streak_exceeded" in health["warnings"]