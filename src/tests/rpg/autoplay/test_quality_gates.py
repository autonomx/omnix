from types import SimpleNamespace

from tests.rpg.autoplay_llm_campaign import (
    _summarize_player_agent_prompt_budget,
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
            "turns": 4,
            "fallback_turns": 0,
        },
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