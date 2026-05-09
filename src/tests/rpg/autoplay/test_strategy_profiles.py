from tests.rpg.autoplay.strategy_profiles import (
    action_diversity_metrics,
    build_strategy_guidance,
    get_strategy_profile,
    list_strategy_profile_ids,
    rerank_suggested_actions_for_strategy,
)


def test_strategy_profiles_are_registered():
    ids = list_strategy_profile_ids()

    assert "balanced_story_player" in ids
    assert "explorer" in ids
    assert get_strategy_profile("missing")["profile_id"] == "balanced_story_player"


def test_action_diversity_metrics_counts_unique_actions():
    transcript = [
        {"player_action": "I observe."},
        {"player_action": "I observe."},
        {"player_action": "I talk to Bran."},
    ]

    metrics = action_diversity_metrics(transcript, window=12)

    assert metrics["action_count"] == 3
    assert metrics["unique_action_count"] == 2
    assert metrics["repeated_actions"]["i observe."] == 2


def test_build_strategy_guidance_activates_antistall_on_churn():
    guidance = build_strategy_guidance(
        strategy="balanced_story_player",
        progress_quality_metrics={
            "churn_only_streak": 4,
            "objective_target_no_meaningful_progress_streak": 4,
        },
        diversity_metrics={"action_diversity_rate": 0.5},
        recent_transcript=[{"player_action": "I ask Bran again."}],
    )

    assert guidance["anti_stall_active"] is True
    assert guidance["recent_actions_to_avoid_repeating"] == ["I ask Bran again."]


def test_rerank_suggested_actions_penalizes_repeated_command_when_stalled():
    suggestions = [
        {
            "action_id": "objective:001",
            "category": "objective",
            "priority": 95,
            "command": "I ask Bran about the witness.",
        },
        {
            "action_id": "explore:001",
            "category": "exploration",
            "priority": 80,
            "command": "I inspect the tavern for signs of the witness.",
        },
    ]
    recent = [{"player_action": "I ask Bran about the witness."} for _ in range(4)]

    ranked = rerank_suggested_actions_for_strategy(
        suggestions,
        strategy="balanced_story_player",
        recent_transcript=recent,
        progress_quality_metrics={
            "churn_only_streak": 4,
            "objective_target_no_meaningful_progress_streak": 4,
        },
    )

    assert ranked[0]["action_id"] == "explore:001"
    assert ranked[0]["anti_stall_applied"] is True


def test_goal_directed_strategy_penalizes_passive_micro_actions_when_stalled():
    actions = [
        {"command": "I listen carefully to Bran for more elaboration.", "category": "social", "priority": 90},
        {"command": "I follow the witness lead toward the road.", "category": "travel", "priority": 70},
        {"command": "I report what I learned to Bran and ask what the next concrete step is.", "category": "objective", "priority": 70},
    ]

    ranked = rerank_suggested_actions_for_strategy(
        actions,
        strategy="goal_directed_quest_runner",
        recent_transcript=[],
        progress_quality_metrics={
            "turn_count": 30,
            "meaningful_progress_rate": 0.05,
            "no_change_turns": 20,
            "churn_only_streak": 0,
            "objective_target_no_meaningful_progress_streak": 0,
        },
    )

    assert ranked[0]["category"] in {"objective", "travel"}
    assert "listen carefully" not in ranked[0]["command"].lower()
    assert ranked[0]["anti_stall_applied"] is True