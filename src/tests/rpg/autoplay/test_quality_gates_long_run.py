from tests.rpg.autoplay_llm_campaign import (
    _summarize_player_journal_quality,
    _summarize_quality_gates,
)


def test_quality_gate_fails_strict_100_turn_repetition():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        capture_console_log=True,
        scenario_seed="tavern_story_seed",
        strict_eval_turns=100,
        max_100turn_repeat_semantic_target_streak=8,
        max_100turn_no_progress_streak=10,
    )
    transcript = [{} for _ in range(100)]
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 100,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {"turns": 100, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 100},
        "player_journal_summary": {"entry_count": 25},
        "player_journal_quality_summary": {"ok": True},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {"line_count": 10, "turn_error_count": 0},
        "story_beat_summary": {"beat_count": 100},
        "quest_progress_summary": {"quest_count": 1},
        "action_diversity_summary": {
            "max_same_semantic_target_streak": {"value": "ask:Bran", "streak": 20},
            "unknown_semantic_rate": 0.0,
        },
        "progress_timeline_summary": {
            "meaningful_progress_rate": 0.2,
            "max_no_progress_streak": 1,
        },
        "long_run_warning_summary": {"ok": False},
        "hundred_turn_eval_summary": {"ok": False},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics={"real_turn_runtime_count": 100},
        summary=summary,
        transcript=transcript,
    )

    assert result["ok"] is False
    assert result["gates"]["strict_100turn_repeat_semantic_target_streak_ok"] is False
    assert result["gates"]["hundred_turn_eval_ok"] is False

def test_quality_gate_fails_strict_background_attach_lag():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        capture_console_log=True,
        scenario_seed="tavern_story_seed",
        strict_eval_turns=100,
        max_100turn_repeat_semantic_target_streak=8,
        max_100turn_no_progress_streak=10,
        background_result_max_turn_lag=5,
        fail_if_background_results_only_finalized=False,
    )
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 100,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {"turns": 100, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 100},
        "player_journal_summary": {"entry_count": 25},
        "player_journal_quality_summary": {"ok": True},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {"line_count": 10, "turn_error_count": 0},
        "story_beat_summary": {"beat_count": 100},
        "quest_progress_summary": {"quest_count": 1},
        "action_diversity_summary": {
            "unknown_semantic_rate": 0.0,
            "max_same_semantic_target_streak": {"value": "ask:Bran", "streak": 1},
        },
        "progress_timeline_summary": {
            "meaningful_progress_rate": 0.5,
            "max_no_progress_streak": 1,
        },
        "long_run_warning_summary": {"ok": True},
        "hundred_turn_eval_summary": {"ok": True},
        "background_result_timing_summary": {
            "ok": False,
            "pre_turn_attach_rate": 0.4,
            "max_attach_lag_turns": 9,
        },
    }

    result = _summarize_quality_gates(
        args=args,
        metrics={"real_turn_runtime_count": 100},
        summary=summary,
        transcript=[{} for _ in range(100)],
    )

    assert result["ok"] is False
    assert result["gates"]["background_result_timing_ok"] is False
    assert result["gates"]["strict_100turn_background_pre_turn_attach_rate_ok"] is False
    assert result["gates"]["strict_100turn_background_attach_lag_ok"] is False

def test_player_journal_quality_flags_internal_codes():
    summary = {
        "player_journal_summary": {
            "entries": [
                {
                    "entry_id": "journal:turn:4",
                    "text": "What stood out: target_not_found no_supported_semantic_action_detected",
                }
            ]
        }
    }

    result = _summarize_player_journal_quality(summary)

    assert result["ok"] is False
    assert result["violation_count"] == 1
    assert "target_not_found" in result["violations"][0]["tokens"]

def test_player_journal_quality_flags_punctuation_and_missing_sections():
    summary = {
        "player_journal_summary": {
            "entries": [
                {
                    "entry_id": "journal:turn:4",
                    "text": "I asked Bran.. Something happened.;",
                }
            ]
        }
    }

    result = _summarize_player_journal_quality(summary)

    assert result["ok"] is False
    assert result["punctuation_violation_count"] == 1
    assert result["missing_section_count"] == 1

def test_quality_gate_fails_strict_100_turn_unknown_semantic_rate():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        capture_console_log=True,
        scenario_seed="tavern_story_seed",
        strict_eval_turns=100,
        max_100turn_repeat_semantic_target_streak=8,
        max_100turn_no_progress_streak=10,
    )
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 100,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {"turns": 100, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 100},
        "player_journal_summary": {"entry_count": 25},
        "player_journal_quality_summary": {"ok": True},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {"line_count": 10, "turn_error_count": 0},
        "story_beat_summary": {"beat_count": 100},
        "quest_progress_summary": {"quest_count": 1},
        "action_diversity_summary": {
            "unknown_semantic_rate": 1.0,
            "max_same_semantic_target_streak": {"value": "unknown:none", "streak": 100},
        },
        "progress_timeline_summary": {
            "meaningful_progress_rate": 0.5,
            "max_no_progress_streak": 1,
        },
        "long_run_warning_summary": {"ok": False},
        "hundred_turn_eval_summary": {"ok": False},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics={"real_turn_runtime_count": 100},
        summary=summary,
        transcript=[{} for _ in range(100)],
    )

    assert result["ok"] is False
    assert result["gates"]["strict_100turn_semantic_action_extraction_ok"] is False

def test_quality_gate_combined_background_uses_timing_tracker_for_pre_turn_drained_jobs():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        capture_console_log=True,
        scenario_seed="tavern_story_seed",
        strict_eval_turns=100,
        max_100turn_repeat_semantic_target_streak=8,
        max_100turn_no_progress_streak=10,
        background_result_max_turn_lag=5,
        fail_if_background_results_only_finalized=False,
    )
    transcript = [{} for _ in range(20)]
    metrics = {"real_turn_runtime_count": 20}
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        # Simulates the old bug: final drain only saw the tail because most jobs
        # had already been consumed pre-turn.
        "background_jobs": {
            "combined_background_llm_jobs": 5,
            "total_jobs": 8,
            "failed_jobs": 3,
            "errors": ["final_drain_timeout"],
        },
        "background_result_timing_summary": {
            "ok": True,
            "jobs_submitted": 20,
            "jobs_attached_total": 20,
            "jobs_attached_pre_turn": 12,
            "jobs_attached_final": 8,
            "missing_job_count": 0,
            "pre_turn_attach_rate": 0.6,
            "max_attach_lag_turns": 7,
            "only_finalized_count": 8,
        },
        "player_agent_trace_summary": {"turns": 20, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 20},
        "player_journal_summary": {"entry_count": 5},
        "player_journal_quality_summary": {"ok": True},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {"line_count": 10, "turn_error_count": 0, "error_count": 0},
        "story_beat_summary": {"beat_count": 20},
        "quest_progress_summary": {"quest_count": 1},
        "action_diversity_summary": {
            "unknown_semantic_rate": 0.0,
            "max_same_semantic_target_streak": {"value": "ask:Bran", "streak": 1},
        },
        "progress_timeline_summary": {
            "meaningful_progress_rate": 0.5,
            "max_no_progress_streak": 1,
        },
        "long_run_warning_summary": {"ok": True},
        "hundred_turn_eval_summary": {"ok": True},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=transcript,
    )

    assert result["gates"]["combined_background_mode_when_requested"] is True

def test_performance_budget_background_counts_can_match_reconciled_background_jobs():
    from tests.rpg.autoplay_llm_campaign import (
        _reconcile_performance_budget_background_llm_counts,
    )

    background_jobs = {
        "source": "background_result_timing_summary",
        "combined_background_llm_jobs": 20,
        "total_jobs": 20,
        "jobs_submitted": 20,
        "jobs_attached_total": 20,
        "jobs_attached_pre_turn": 12,
        "jobs_attached_final": 8,
        "failed_jobs": 3,
    }
    performance = _reconcile_performance_budget_background_llm_counts(
        performance_budget_summary={
            "background_llm": {
                "combined_background_llm_jobs": 6,
                "total_jobs": 8,
            }
        },
        background_jobs=background_jobs,
        background_result_timing_summary={
            "jobs_submitted": 20,
            "jobs_attached_total": 20,
            "jobs_attached_pre_turn": 12,
            "jobs_attached_final": 8,
        },
    )

    assert (
        performance["background_llm"]["combined_background_llm_jobs"]
        == background_jobs["combined_background_llm_jobs"]
    )
    assert performance["background_llm"]["total_jobs"] == background_jobs["total_jobs"]

def test_final_lifecycle_quality_gates_fail_when_lifecycle_red():
    from tests.rpg.autoplay_llm_campaign import _final_lifecycle_quality_gates

    summary = {
        "requested_turns": 20,
        "turns_executed": 20,
        "quality_gate_summary": {"gates": {"existing_gate": True}, "ok": True},
        "strict_progress_health_summary": {"ok": False},
        "post_transition_action_quality_summary": {"ok": False},
        "objective_progression_summary": {"ok": False},
        "repeated_affordance_loop_summary": {"ok": False},
    }

    gates = _final_lifecycle_quality_gates(summary)

    assert gates["ok"] is False
    assert gates["gates"]["strict_progress_health_ok"] is False
    assert gates["gates"]["post_transition_action_quality_ok"] is False
    assert gates["gates"]["objective_progression_present_ok"] is False
    assert gates["gates"]["repeated_affordance_loop_ok"] is False

def test_guard_quest_summary_source_replaces_false_latest_quest_progress_source():
    from tests.rpg.autoplay_llm_campaign import _guard_quest_summary_source

    latest_state = {
        "witness_search_facts": {
            "inspected_side_door": True,
            "followed_road": True,
            "reported_to_bran": True,
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:witness:pursue_bandit_trail": {"turn_index": 4}
            }
        },
    }
    summary = {
        "quest_progress_summary": {
            "source": "latest_state.quest_progress",
            "quest_count": 1,
            "quests": [],
        }
    }

    _guard_quest_summary_source(summary, latest_state)

    assert summary["quest_progress_summary"]["source"] != "latest_state.quest_progress"

def test_pre_turn_advisory_promotion_performance_summary_flags_slow_event():
    from tests.rpg.autoplay_llm_campaign import (
        _pre_turn_advisory_promotion_performance_summary,
    )

    summary = _pre_turn_advisory_promotion_performance_summary(
        [
            {
                "pre_turn_advisory_promotion_result": {
                    "elapsed_ms": 9000,
                    "fast_pre_turn": True,
                    "turns": 1,
                }
            }
        ],
        slow_events=[{"turn_index": 3, "elapsed_ms": 9000}],
        auto_disabled=True,
        disable_reason="slow_pre_turn_advisory_promotion:9000ms",
    )

    assert summary["ok"] is False
    assert summary["slow_event_count"] == 1
    assert summary["auto_disabled"] is True
    assert summary["max_elapsed_ms"] == 9000

def test_pre_turn_advisory_perf_ok_when_zero_slow_events_and_low_elapsed():
    from tests.rpg.autoplay_llm_campaign import (
        _pre_turn_advisory_promotion_performance_summary,
    )

    summary = _pre_turn_advisory_promotion_performance_summary(
        [
            {
                "pre_turn_advisory_promotion_result": {
                    "elapsed_ms": 9,
                    "fast_pre_turn": True,
                    "slow_guard_ms": 5000,
                }
            }
        ],
        slow_events=[],
        auto_disabled=False,
        disable_reason="",
    )

    assert summary["ok"] is True
    assert summary["max_elapsed_ms"] == 9
    assert summary["slow_event_count"] == 0

def test_final_lifecycle_quality_gates_fail_when_required_fields_missing():
    from tests.rpg.autoplay_llm_campaign import _final_lifecycle_quality_gates

    summary = {
        "requested_turns": 20,
        "quality_gate_summary": {"ok": True, "gates": {}},
    }

    result = _final_lifecycle_quality_gates(summary)

    assert result["ok"] is False
    assert result["gates"]["final_lifecycle_summary_fields_present_ok"] is False
    assert "final_lifecycle_summary_fields_present_ok" in result["failed_gates"]

def test_authoritative_final_lifecycle_summary_populates_required_fields():
    from types import SimpleNamespace

    from tests.rpg.autoplay_llm_campaign import (
        REQUIRED_FINAL_LIFECYCLE_SUMMARY_FIELDS,
        _build_authoritative_final_lifecycle_summary,
    )

    runtime_state = {
        "quest_progress": {
            "quests": {
                "quest:test": {
                    "quest_id": "quest:test",
                    "title": "Test Quest",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:test",
                            "summary": "Inspect the test clue.",
                            "status": "active",
                            "completed": False,
                        }
                    ],
                }
            }
        },
        "dialogue_state": {"recent_exchanges": [{"npc": "npc:test"}]},
        "objective_progression_log": [
            {"objective_id": "objective:test", "matched": True, "partial": True}
        ],
        "quest_reconciliation_log": [{"changed": False}],
        "quest_handoff_log": [{"quest_id": "quest:test"}],
        "autoplay_story_hook_state": {"fired_hooks": {"hook:test": {}}},
        "location_history": [{"location_id": "location:test"}],
        "recent_turns": [{"turn": 1, "player_action": "I inspect the test clue."}],
        "action_history": [{"turn": 1, "player_action": "I inspect the test clue."}],
    }

    summary = {
        "requested_turns": 20,
        "health": {
            "progress_quality": {
                "ok": True,
                "metrics": {
                    "meaningful_progress_rate": 0.2,
                    "meaningful_turns": 4,
                    "no_change_turns": 2,
                    "churn_only_turns": 1,
                },
            }
        },
        "quality_gate_summary": {"ok": True, "gates": {}},
    }

    final = _build_authoritative_final_lifecycle_summary(
        args=SimpleNamespace(capture_console_log=True),
        summary=summary,
        runtime_state=runtime_state,
        transcript=[{"turn": 1, "player_action": "I inspect the test clue."}],
        background_drain_events=[
            {
                "pre_turn_advisory_promotion_result": {
                    "elapsed_ms": 5,
                    "fast_pre_turn": True,
                }
            }
        ],
        pre_turn_advisory_promotion_slow_events=[],
        pre_turn_advisory_promotion_auto_disabled=False,
        pre_turn_advisory_promotion_disable_reason="",
    )

    for key in REQUIRED_FINAL_LIFECYCLE_SUMMARY_FIELDS:
        assert key in final
        assert final[key] not in (None, {}, [])

    assert final["latest_state"]["quest_progress"]["quests"]
    assert final["quality_gate_summary"]["gates"]["final_lifecycle_summary_fields_present_ok"] is True
    assert final["ok"] == final["quality_gate_summary"]["ok"]

def test_assert_final_lifecycle_summary_authority_raises_on_false_green():
    import pytest

    from tests.rpg.autoplay_llm_campaign import (
        _assert_final_lifecycle_summary_authority,
    )

    summary = {
        "ok": True,
        "quality_gate_summary": {"ok": True, "gates": {}},
    }

    with pytest.raises(RuntimeError, match="final_lifecycle_summary_missing_fields"):
        _assert_final_lifecycle_summary_authority(summary)
