from tests.rpg.autoplay.parallel_pipeline import (
    _queue_summary,
    attach_background_results_to_transcript,
)
from tests.rpg.autoplay_llm_campaign import _summarize_performance_budget


def test_queue_summary_computes_wait_run_total():
    summary = _queue_summary(
        [
            {"queue_timing": {"queue_wait_ms": 10, "run_ms": 100, "total_ms": 110}},
            {"queue_timing": {"queue_wait_ms": 30, "run_ms": 300, "total_ms": 330}},
        ]
    )
    assert summary["count"] == 2
    assert summary["avg_queue_wait_ms"] == 20.0
    assert summary["max_run_ms"] == 300.0


def test_attach_combined_background_llm_populates_narration_and_advisory_slots():
    transcript = [
        {
            "turn_index": 1,
            "narration": "pending",
            "turn_result": {
                "narration_payload": {"source": "deferred_runtime_narration_pending"}
            },
        }
    ]
    result = {
        "ok": True,
        "kind": "combined_background_llm",
        "session_id": "s",
        "turn_index": 1,
        "source": "provider_combined_background_llm",
        "narration": "The tavern quiets.",
        "npc": {},
        "narration_payload": {
            "source": "provider_runtime_narration",
            "narration": "The tavern quiets.",
        },
        "candidate_count": 1,
        "candidates": [{"kind": "future_hook"}],
        "advisory_summary": {"total": 1},
        "worker_ms": 1000.0,
        "queue_timing": {"queue_wait_ms": 1, "run_ms": 1000, "total_ms": 1001},
    }

    summary = attach_background_results_to_transcript(transcript, [result])

    assert summary["combined_background_llm_jobs"] == 1
    assert transcript[0]["resolved_narration"] == "The tavern quiets."
    assert transcript[0]["deferred_narration_result"]["narration_payload"]["source"] == "provider_runtime_narration"
    assert transcript[0]["deferred_advisory_result"]["candidate_count"] == 1
    assert transcript[0]["turn_result"]["narration_payload"]["source"] == "deferred_runtime_narration_pending"
    assert summary["provider_queue_by_kind"]["combined_background_llm"]["count"] == 1


def test_performance_budget_splits_live_autoplay_and_background():
    transcript = [
        {
            "performance": {
                "manual_turn_ms": 50.0,
                "human_playable_blocking_ms": 50.0,
                "player_agent_ms": 1000.0,
                "playable_blocking_ms": 1050.0,
            }
        }
    ]
    background = {
        "total_jobs": 1,
        "narration_jobs": 0,
        "advisory_jobs": 0,
        "combined_background_llm_jobs": 1,
        "background_job_seconds": 1.0,
        "provider_queue_summary": {"avg_queue_wait_ms": 0.0, "avg_run_ms": 1000.0},
    }
    summary = _summarize_performance_budget(transcript=transcript, background_summary=background)
    assert summary["live_blocking"]["avg_human_playable_blocking_ms"] == 50.0
    assert summary["autoplay_only"]["avg_player_agent_ms"] == 1000.0
    assert summary["background_llm"]["combined_background_llm_jobs"] == 1