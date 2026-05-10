from types import SimpleNamespace

from tests.rpg.autoplay_llm_campaign import (
    _final_lifecycle_quality_gates,
    _summarize_manual_turn_errors,
    _summarize_npc_arc_progression,
    _summarize_player_agent_prompt_budget,
    _summarize_player_journal_quality,
    _summarize_profile_grounded_output,
    _summarize_promotion_target_grounding,
    _summarize_quality_gates,
)


def test_summarize_player_agent_prompt_budget_counts_cache_hits():
    summary = _summarize_player_agent_prompt_budget(
        [
            {
                "source": "llm_player_agent",
                "cache_hit": False,
                "prompt_metrics": {"total_chars": 1000, "estimated_tokens": 250},
            },
            {
                "source": "llm_player_agent",
                "cache_hit": True,
                "prompt_metrics": {"total_chars": 500, "estimated_tokens": 125},
            },
        ]
    )
    assert summary["count"] == 2
    assert summary["cache_hits"] == 1
    assert summary["avg_total_chars"] == 750


def test_quality_gates_pass_for_fast_combined_run():
    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        scenario_seed="",
    )
    metrics = {"real_turn_runtime_count": 2}
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 80,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 2,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {
            "turns": 2,
            "fallback_turns": 0,
        },
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
        "campaign_calendar_summary": {"turns_tracked": 2},
        "player_journal_summary": {"entry_count": 1},
        "npc_evolution_profile_persistence_summary": {"ok": True},
        "npc_profile_load_summary": {"ok": True, "turns_with_profiles": 0},
        "profile_grounded_output_summary": {"available_turns": 0},
        "npc_arc_progression_summary": {"ok": True},
        "deferred_advisory_promotion_summary": {"mutated_authoritative_state": False},
        "console_log_summary": {"line_count": 1},
        "action_diversity_summary": {
            "max_same_semantic_target_streak": {"streak": 1}
        },
        "progress_timeline_summary": {
            "meaningful_progress_rate": 1.0,
            "max_no_progress_streak": 0,
        },
        "long_run_warning_summary": {"ok": True},
        "hundred_turn_eval_summary": {"ok": True},
        "background_result_timing_summary": {"ok": True, "pre_turn_attach_rate": 1.0, "max_attach_lag_turns": 0},
    }
    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=[{}, {}],
    )
    assert result["ok"] is True


def test_quality_gates_can_read_background_jobs_from_final_summary():
    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        scenario_seed="",
    )
    metrics = {"real_turn_runtime_count": 4}
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 44,
                "max_human_playable_blocking_ms": 49,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 4,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {
            "turns": 2,
            "fallback_turns": 0,
        },
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
        "campaign_calendar_summary": {
            "turns_tracked": 4,
        },
        "player_journal_summary": {
            "entry_count": 1,
        },
        "console_log_summary": {"line_count": 1},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=[{}, {}, {}, {}],
    )

    assert result["ok"] is True
    assert result["gates"]["combined_background_mode_when_requested"] is True


def test_quality_gates_fallback_to_performance_budget_background_llm():
    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        scenario_seed="",
    )
    metrics = {"real_turn_runtime_count": 2}
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 80,
            },
            "background_llm": {
                "combined_background_llm_jobs": 2,
                "narration_jobs": 0,
                "advisory_jobs": 0,
            },
        },
        "player_agent_trace_summary": {
            "turns": 2,
            "fallback_turns": 0,
        },
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
        "npc_evolution_profile_persistence_summary": {"ok": True},
        "npc_profile_load_summary": {"ok": True, "turns_with_profiles": 0},
        "profile_grounded_output_summary": {"available_turns": 0},
        "npc_arc_progression_summary": {"ok": True},
        "deferred_advisory_promotion_summary": {"mutated_authoritative_state": False},
        "campaign_calendar_summary": {
            "turns_tracked": 2,
        },
        "player_journal_summary": {
            "entry_count": 1,
        },
        "console_log_summary": {"line_count": 1},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=[{}, {}],
    )

    assert result["ok"] is True
    assert result["gates"]["combined_background_mode_when_requested"] is True


def test_final_lifecycle_gates_require_campaign_state_commit():
    summary = {
        "requested_turns": 20,
        "quality_gate_summary": {"ok": True, "gates": {}},
        "latest_state": {"quest_progress": {"quests": {}}},
        "quest_progress_summary": {"active_count": 0, "completed_count": 0},
        "objective_progression_summary": {"matched_count": 1, "ok": True},
        "quest_reconciliation_summary": {"ok": True},
        "quest_handoff_summary": {"ok": True},
        "final_state_field_coverage_summary": {"ok": True},
        "strict_progress_health_summary": {"ok": True},
        "post_transition_action_quality_summary": {"ok": True},
        "repeated_affordance_loop_summary": {"ok": True},
        "pre_turn_advisory_promotion_performance_summary": {"ok": True},
        "campaign_state_commit_summary": {"ok": False},
        "campaign_stale_state_summary": {"ok": False},
        "campaign_state_commit_performance_summary": {"ok": True},
    }

    result = _final_lifecycle_quality_gates(summary)

    assert result["ok"] is False
    assert result["gates"]["campaign_state_commit_ok"] is False
    assert result["gates"]["campaign_state_not_stale_ok"] is False


def test_promotion_target_grounding_summary_dedupes_cumulative_runtime_state():
    transcript = [
        {
            "turn_index": 2,
            "deferred_advisory_promotion_result": {
                "decisions": [
                    {
                        "candidate_id": "adv:1:relationship_delta:a",
                        "status": "accepted",
                        "reason": "accepted_by_deterministic_gate",
                        "target_grounding": {
                            "grounded": True,
                            "npc_id": "Bran",
                            "reason": "explicit_known_target",
                        },
                    }
                ]
            },
            "runtime_state": {
                "deferred_advisory": {
                    "accepted": [
                        {
                            "candidate_id": "adv:1:relationship_delta:a",
                            "kind": "relationship_delta",
                        }
                    ],
                    "rejected": [],
                }
            },
        },
        {
            "turn_index": 3,
            "deferred_advisory_promotion_result": {
                "decisions": [
                    {
                        "candidate_id": "adv:1:relationship_delta:a",
                        "status": "accepted",
                        "reason": "accepted_by_deterministic_gate",
                        "target_grounding": {
                            "grounded": True,
                            "npc_id": "Bran",
                            "reason": "explicit_known_target",
                        },
                    },
                    {
                        "candidate_id": "adv:2:relationship_delta:b",
                        "status": "rejected",
                        "reason": "relationship_target_not_present_or_unknown",
                        "target_grounding": {
                            "grounded": False,
                            "npc_id": "",
                            "reason": "no_deterministic_target",
                        },
                    },
                ]
            },
            "runtime_state": {
                "deferred_advisory": {
                    "accepted": [
                        {
                            "candidate_id": "adv:1:relationship_delta:a",
                            "kind": "relationship_delta",
                        }
                    ],
                    "rejected": [
                        {
                            "candidate_id": "adv:2:relationship_delta:b",
                            "kind": "relationship_delta",
                        }
                    ],
                }
            },
        },
        {
            "turn_index": 4,
            "runtime_state": {
                "deferred_advisory": {
                    "accepted": [
                        {
                            "candidate_id": "adv:1:relationship_delta:a",
                            "kind": "relationship_delta",
                        }
                    ],
                    "rejected": [
                        {
                            "candidate_id": "adv:2:relationship_delta:b",
                            "kind": "relationship_delta",
                        }
                    ],
                }
            },
        },
    ]

    summary = _summarize_promotion_target_grounding(transcript)

    assert summary["relationship_accepted"] == 1
    assert summary["relationship_rejected"] == 1
    assert summary["unique_relationship_accepted"] == 1
    assert summary["unique_relationship_rejected"] == 1
    assert summary["grounded"] == 1
    assert summary["ungrounded"] == 1
    assert summary["by_reason"]["explicit_known_target"] == 1
    assert summary["by_reason"]["no_deterministic_target"] == 1
    assert len(summary["examples"]) == 2


def test_summarize_profile_grounded_output_detects_loaded_profile_context_and_reference():
    transcript = [
        {
            "turn_index": 2,
            "combined_background_llm_result": {
                "narration": "Bran watches with guarded trust as the room settles.",
                "narration_payload": {
                    "npc": {"speaker": "Bran", "line": "I remember what you asked about the mill."}
                },
                "profile_context_summary": {
                    "available": True,
                    "npc_count": 1,
                    "npc_ids": ["Bran"],
                    "arc_stages": {"Bran": "trusting"},
                },
            },
            "runtime_state": {
                "npc_evolution": {
                    "loaded_profiles": {
                        "Bran": {
                            "profile": {
                                "npc_id": "Bran",
                                "arc_stage": "trusting",
                                "axes": {"trust": 4},
                                "memories": [
                                    {"summary": "Bran remembers the player asking about the mill."}
                                ],
                                "future_hooks": [],
                            }
                        }
                    }
                }
            },
        }
    ]

    summary = _summarize_profile_grounded_output(transcript)

    assert summary["available_turns"] == 1
    assert summary["referenced_turns"] == 1
    assert summary["loaded_npc_ids"] == ["Bran"]
    assert summary["by_npc"]["Bran"]["referenced_turns"] == 1


def test_quality_gate_requires_profile_context_when_profiles_loaded():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        scenario_seed="",
    )
    metrics = {"real_turn_runtime_count": 1}
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 1,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {
            "turns": 2,
            "fallback_turns": 0,
        },
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
        "campaign_calendar_summary": {"turns_tracked": 2},
        "player_journal_summary": {"entry_count": 1},
        "npc_evolution_profile_persistence_summary": {"ok": True},
        "npc_profile_load_summary": {"ok": True, "turns_with_profiles": 1},
        "profile_grounded_output_summary": {"available_turns": 1},
        "npc_arc_progression_summary": {"ok": True},
        "deferred_advisory_promotion_summary": {"mutated_authoritative_state": False},
        "campaign_calendar_summary": {"turns_tracked": 1},
        "player_journal_summary": {"entry_count": 1},
        "console_log_summary": {"line_count": 1},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=[{}],
    )

    assert result["ok"] is True
    assert result["gates"]["profile_grounding_context_available_when_profiles_loaded"] is True


def test_summarize_npc_arc_progression_detects_stage_change():
    transcript = [
        {
            "turn_index": 3,
            "npc_evolution_consumption_result": {
                "consume_decisions": [
                    {
                        "ok": True,
                        "npc_id": "Bran",
                        "signal_id": "s1",
                        "kind": "relationship_delta",
                        "stage_changed": True,
                        "arc_stage_before": "stable",
                        "arc_stage_after": "trusting",
                        "milestone": {
                            "milestone_id": "m1",
                            "from": "stable",
                            "to": "trusting",
                            "reason": "relationship_delta:trust",
                            "signal_id": "s1",
                        },
                    }
                ]
            },
            "npc_evolution_summary": {
                "duplicate_milestone_ids": [],
                "out_of_bounds_axes": [],
            },
        }
    ]

    summary = _summarize_npc_arc_progression(transcript)

    assert summary["ok"] is True
    assert summary["stage_change_count"] == 1
    assert summary["by_npc"]["Bran"]["stage_changes"] == 1


def test_manual_turn_error_summary_detects_manual_runtime_error():
    summary = _summarize_manual_turn_errors(
        [
            {
                "turn_index": 1,
                "manual_turn_summary": {
                    "error": "UnboundLocalError: cannot access local variable 'turn_contract'",
                },
            }
        ]
    )

    assert summary["ok"] is False
    assert summary["error_count"] == 1
    assert "turn_contract" in summary["errors"][0]["error"]


def test_quality_gate_fails_on_console_turn_errors():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
    )
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 1,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {"turns": 1, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 1},
        "player_journal_summary": {"entry_count": 1},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {
            "turn_error_count": 1,
            "turn_errors": ["TURN 1 ERROR: boom"],
        },
    }

    result = _summarize_quality_gates(
        args=args,
        metrics={"real_turn_runtime_count": 1},
        summary=summary,
        transcript=[{}],
    )

    assert result["ok"] is False
    assert result["gates"]["console_turn_errors_absent"] is False


def test_quality_gate_requires_quest_progress_for_tavern_seed():
    from types import SimpleNamespace

    args = SimpleNamespace(
        background_llm_mode="combined",
        max_player_agent_fallback_rate=0.25,
        capture_console_log=True,
        scenario_seed="tavern_story_seed",
    )
    summary = {
        "performance_budget_summary": {
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            }
        },
        "background_jobs": {
            "combined_background_llm_jobs": 1,
            "narration_jobs": 0,
            "advisory_jobs": 0,
        },
        "player_agent_trace_summary": {"turns": 1, "fallback_turns": 0},
        "campaign_calendar_summary": {"turns_tracked": 1},
        "player_journal_summary": {"entry_count": 1},
        "manual_turn_error_summary": {"ok": True, "error_count": 0},
        "console_log_summary": {"line_count": 1, "turn_error_count": 0},
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
    }

    result = _summarize_quality_gates(
        args=args,
        metrics={"real_turn_runtime_count": 1},
        summary=summary,
        transcript=[{}],
    )

    assert result["ok"] is False
    assert result["gates"]["tavern_story_seed_has_quest_progress"] is False


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

    from tests.rpg.autoplay_llm_campaign import _summarize_quality_gates

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