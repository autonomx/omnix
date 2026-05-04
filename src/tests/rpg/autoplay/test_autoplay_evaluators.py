from tests.rpg.autoplay.evaluators import (
    compute_progress_metrics,
    detect_repeated_action_loop,
    evaluate_autoplay_health,
)


def test_detect_repeated_action_loop_flags_streak():
    transcript = [{"player_action": "I observe."} for _ in range(6)]

    result = detect_repeated_action_loop(transcript, max_repeated_actions=5)

    assert result["ok"] is False
    assert result["reason"] == "repeated_action_loop"


def test_compute_progress_metrics_counts_runtime_errors():
    transcript = [
        {"player_action": "A", "runtime_error": ""},
        {"player_action": "B", "runtime_error": "boom"},
    ]

    metrics = compute_progress_metrics(transcript)

    assert metrics["turn_count"] == 2
    assert metrics["runtime_errors"] == 1


def test_evaluate_autoplay_health_ok_for_simple_transcript():
    transcript = [
        {"player_action": "I observe."},
        {"player_action": "I talk to Bran."},
    ]

    health = evaluate_autoplay_health(transcript, latest_context={"suggested_actions": [{"x": 1}]})

    assert health["ok"] is True


def test_evaluate_autoplay_health_can_fail_on_compatibility_runtime():
    transcript = [
        {
            "player_action": "I observe.",
            "turn_result": {"compatibility_turn_runtime": True},
        }
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
        allow_compatibility_turn_runtime=False,
    )

    assert health["ok"] is False
    assert "compatibility_turn_runtime_used" in health["warnings"]


def test_evaluate_autoplay_health_can_fail_on_fallback_rate():
    transcript = [
        {
            "player_action": "I observe.",
            "selected_player_action": {"fallback": True},
        },
        {
            "player_action": "I talk to Bran.",
            "selected_player_action": {"fallback": True},
        },
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
        max_player_agent_fallback_rate=0.5,
    )

    assert health["ok"] is False
    assert "player_agent_fallback_rate_exceeded" in health["warnings"]


def test_evaluate_autoplay_health_can_fail_on_no_progress_streak():
    transcript = [
        {"player_action": "A", "progress_delta": {"changed": False, "categories": []}},
        {"player_action": "B", "progress_delta": {"changed": False, "categories": []}},
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
        max_no_progress_turns=1,
    )

    assert health["ok"] is False
    assert "no_progress_turn_limit_exceeded" in health["warnings"]


def test_evaluate_autoplay_health_can_fail_on_checkpoint_failure():
    transcript = [
        {
            "player_action": "A",
            "save_load_checkpoint": {"ok": False},
        }
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
    )

    assert health["ok"] is False
    assert "save_load_checkpoint_failed" in health["warnings"]


def test_evaluate_autoplay_health_can_fail_on_state_bounds_warning():
    transcript = [
        {
            "player_action": "A",
            "state_bounds": {"warnings": ["state_size_limit_exceeded"]},
        }
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
    )

    assert health["ok"] is False
    assert "state_bounds_warning" in health["warnings"]


def test_evaluate_autoplay_health_can_fail_on_action_diversity():
    transcript = [
        {"player_action": "I observe."},
        {"player_action": "I observe."},
        {"player_action": "I observe."},
    ]

    health = evaluate_autoplay_health(
        transcript,
        latest_context={"suggested_actions": [{"x": 1}]},
        min_action_diversity_rate=0.75,
    )

    assert health["ok"] is False
    assert "action_diversity_rate_below_threshold" in health["warnings"]