from tests.rpg.autoplay.progress_quality import compute_progress_quality_metrics
from tests.rpg.autoplay.strategy_profiles import build_strategy_guidance


def test_live_progress_quality_metrics_activate_antistall_after_targeted_churn():
    transcript = [
        {
            "player_action": "I ask Bran about the witness.",
            "progress_quality": {
                "quality": "churn_only",
                "churn_only": ["state_changed"],
                "objective_targeted": True,
                "meaningful": [],
            },
        },
        {
            "player_action": "I ask Bran again about the witness.",
            "progress_quality": {
                "quality": "churn_only",
                "churn_only": ["state_changed"],
                "objective_targeted": True,
                "meaningful": [],
            },
        },
        {
            "player_action": "I ask another patron about the witness.",
            "progress_quality": {
                "quality": "churn_only",
                "churn_only": ["state_changed"],
                "objective_targeted": True,
                "meaningful": [],
            },
        },
    ]

    metrics = compute_progress_quality_metrics(transcript)
    guidance = build_strategy_guidance(
        strategy="balanced_story_player",
        progress_quality_metrics=metrics,
        diversity_metrics={"action_diversity_rate": 1.0},
        recent_transcript=transcript,
    )

    assert metrics["churn_only_streak"] == 3
    assert metrics["objective_target_no_meaningful_progress_streak"] == 3
    assert guidance["anti_stall_active"] is True
    assert "Do not repeat the same action or same question." in guidance["hints"]