from types import SimpleNamespace

from tests.rpg.autoplay_llm_campaign import (
    _summarize_manual_turn_errors,
    _summarize_npc_arc_progression,
    _summarize_player_agent_prompt_budget,
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
        "campaign_calendar_summary": {
            "turns_tracked": 4,
        },
        "player_journal_summary": {
            "entry_count": 1,
        },
        "story_beat_summary": {"beat_count": 1},
        "quest_progress_summary": {"quest_count": 0},
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
    }

    result = _summarize_quality_gates(
        args=args,
        metrics=metrics,
        summary=summary,
        transcript=[{}, {}],
    )

    assert result["ok"] is True
    assert result["gates"]["combined_background_mode_when_requested"] is True


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
        "npc_profile_load_summary": {"ok": True, "turns_with_profiles": 0},
        "profile_grounded_output_summary": {"available_turns": 0},
        "npc_arc_progression_summary": {"ok": True},
        "deferred_advisory_promotion_summary": {"mutated_authoritative_state": False},
        "npc_profile_load_summary": {
            "ok": True,
            "turns_with_profiles": 1,
        },
        "profile_grounded_output_summary": {
            "available_turns": 1,
        },
        "campaign_calendar_summary": {
            "turns_tracked": 1,
        },
        "player_journal_summary": {
            "entry_count": 1,
        },
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