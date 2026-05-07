from tests.rpg.autoplay_llm_campaign import (
    _new_background_result_timing_tracker,
    _summarize_background_result_timing,
    _track_background_attach,
    _track_background_submit,
)


class _DoneFuture:
    def __init__(self, payload):
        self.payload = payload

    def done(self):
        return True

    def result(self, timeout=0):
        return self.payload


def test_background_result_timing_summarizes_pre_turn_and_final_attach():
    tracker = _new_background_result_timing_tracker()
    _track_background_submit(tracker, job_id="job1", turn_index=1)
    _track_background_submit(tracker, job_id="job2", turn_index=2)
    _track_background_attach(
        tracker,
        job_id="job1",
        source_turn=1,
        attach_turn=3,
        phase="pre_turn",
    )
    _track_background_attach(
        tracker,
        job_id="job2",
        source_turn=2,
        attach_turn=8,
        phase="final",
    )

    summary = _summarize_background_result_timing(
        tracker,
        turn_count=8,
        strict_eval_turns=100,
        max_turn_lag=5,
    )

    assert summary["jobs_submitted"] == 2
    assert summary["jobs_attached_total"] == 2
    assert summary["jobs_attached_pre_turn"] == 1
    assert summary["jobs_attached_final"] == 1
    assert summary["pre_turn_attach_rate"] == 0.5
    assert summary["max_attach_lag_turns"] == 6
    # Smoke mode: lag is warning-only, ok remains true.
    assert summary["ok"] is True


def test_background_result_timing_fails_strict_when_only_finalized():
    tracker = _new_background_result_timing_tracker()
    for turn in range(1, 101):
        job_id = f"job{turn}"
        _track_background_submit(tracker, job_id=job_id, turn_index=turn)
        _track_background_attach(
            tracker,
            job_id=job_id,
            source_turn=turn,
            attach_turn=100,
            phase="final",
        )

    summary = _summarize_background_result_timing(
        tracker,
        turn_count=100,
        strict_eval_turns=100,
        max_turn_lag=5,
    )

    assert summary["strict_100_turn_mode"] is True
    assert summary["ok"] is False
    assert summary["jobs_attached_pre_turn"] == 0
    assert summary["only_finalized_count"] == 100
    assert any(w["code"] == "background_results_only_finalized" for w in summary["warnings"])


def test_registry_result_resolver_reads_done_future():
    from tests.rpg.autoplay_llm_campaign import (
        _new_background_job_registry,
        _register_background_job,
        _try_get_combined_background_result_from_registry,
    )

    registry = _new_background_job_registry()
    future = _DoneFuture({"combined_background_llm_result": {"narration": "done"}})

    _register_background_job(
        registry,
        job_id="job1",
        turn_index=1,
        handle=future,
        pipeline=None,
    )

    result = _try_get_combined_background_result_from_registry(
        registry=registry,
        pipeline=None,
        job_id="job1",
    )

    assert result["combined_background_llm_result"]["narration"] == "done"


def test_background_drain_attaches_done_future_result():
    from tests.rpg.autoplay_llm_campaign import (
        _drain_completed_background_jobs_for_transcript,
        _new_background_job_registry,
        _new_background_result_timing_tracker,
        _register_background_job,
        _track_background_submit,
    )

    registry = _new_background_job_registry()
    tracker = _new_background_result_timing_tracker()
    transcript = [
        {
            "turn_index": 1,
            "combined_background_llm_job_id": "job1",
        }
    ]

    _track_background_submit(tracker, job_id="job1", turn_index=1)
    _register_background_job(
        registry,
        job_id="job1",
        turn_index=1,
        handle=_DoneFuture({"combined_background_llm_result": {"narration": "done"}}),
        pipeline=None,
    )

    event = _drain_completed_background_jobs_for_transcript(
        pipeline=object(),
        job_registry=registry,
        transcript=transcript,
        current_turn=2,
        phase="pre_turn",
        wait_ms=0,
        timing_tracker=tracker,
    )

    assert event["checked"] == 1
    assert event["ready"] == 1
    assert event["attached"] == 1
    assert event["pipeline_completed_drained"] >= 0
    assert transcript[0]["combined_background_llm_result"]["narration"] == "done"


def test_pipeline_drain_completed_returns_finished_future_without_final_drain():
    from tests.rpg.autoplay.parallel_pipeline import AutoplayBackgroundPipeline

    pipeline = AutoplayBackgroundPipeline(background_workers=1, provider_workers=1)
    future = pipeline._provider_executor.submit(
        lambda: {
            "ok": True,
            "kind": "combined_background_llm",
            "job_id": "combined_background_llm:s:1",
            "turn_index": 1,
            "narration": "done",
        }
    )
    pipeline._register_future("combined_background_llm:s:1", future)

    # The future should become available without waiting for final drain.
    import time
    for _ in range(20):
        results = pipeline.drain_completed()
        if results:
            break
        time.sleep(0.01)

    pipeline.shutdown()

    assert results
    assert results[0]["job_id"] == "combined_background_llm:s:1"
    assert results[0]["narration"] == "done"


def test_pipeline_drain_timeout_marks_unfinished_future():
    import time
    from tests.rpg.autoplay.parallel_pipeline import AutoplayBackgroundPipeline

    pipeline = AutoplayBackgroundPipeline(background_workers=1, provider_workers=1)

    def slow_job():
        time.sleep(10)
        return {"ok": True, "job_id": "slow", "narration": "late"}

    future = pipeline._provider_executor.submit(slow_job)
    pipeline._register_future("slow", future)

    results = pipeline.drain(timeout_seconds=0.01, cancel_unfinished=True)
    pipeline.shutdown(wait=False, cancel_futures=True)

    assert results
    assert results[0]["job_id"] == "slow"
    assert results[0]["ok"] is False
    assert results[0]["kind"] == "background_timeout"


def test_reconciled_background_jobs_counts_pre_turn_drained_jobs():
    from tests.rpg.autoplay_llm_campaign import _summarize_reconciled_background_jobs

    summary = _summarize_reconciled_background_jobs(
        existing_background_jobs={
            "combined_background_llm_jobs": 5,
            "total_jobs": 8,
            "failed_jobs": 3,
            "errors": ["final_drain_timeout"],
        },
        background_results=[
            {"ok": False, "kind": "background_timeout", "job_id": "job18", "error": "final_drain_timeout"},
            {"ok": False, "kind": "background_timeout", "job_id": "job19", "error": "final_drain_timeout"},
            {"ok": False, "kind": "background_timeout", "job_id": "job20", "error": "final_drain_timeout"},
        ],
        background_result_timing_summary={
            "jobs_submitted": 20,
            "jobs_attached_total": 20,
            "jobs_attached_pre_turn": 12,
            "jobs_attached_final": 8,
            "missing_job_count": 0,
        },
        transcript=[
            {"combined_background_llm_result": {"ok": True, "job_id": f"job{idx}"}}
            for idx in range(1, 18)
        ] + [
            {
                "combined_background_llm_result": {
                    "ok": False,
                    "kind": "background_timeout",
                    "job_id": "job18",
                    "error": "final_drain_timeout",
                }
            },
            {
                "combined_background_llm_result": {
                    "ok": False,
                    "kind": "background_timeout",
                    "job_id": "job19",
                    "error": "final_drain_timeout",
                }
            },
            {
                "combined_background_llm_result": {
                    "ok": False,
                    "kind": "background_timeout",
                    "job_id": "job20",
                    "error": "final_drain_timeout",
                }
            },
        ],
    )

    assert summary["source"] == "background_result_timing_summary"
    assert summary["combined_background_llm_jobs"] == 20
    assert summary["total_jobs"] == 20
    assert summary["jobs_attached_pre_turn"] == 12
    assert summary["jobs_attached_final"] == 8
    assert summary["pre_turn_drain_accounted"] is True
    assert summary["timeout_job_count"] >= 3
    assert "final_drain_timeout" in summary["errors"]


def test_reconcile_performance_budget_background_llm_counts_uses_reconciled_jobs():
    from tests.rpg.autoplay_llm_campaign import (
        _reconcile_performance_budget_background_llm_counts,
    )

    result = _reconcile_performance_budget_background_llm_counts(
        performance_budget_summary={
            "live_blocking": {
                "avg_human_playable_blocking_ms": 50,
                "max_human_playable_blocking_ms": 90,
            },
            "background_llm": {
                "combined_background_llm_jobs": 6,
                "total_jobs": 8,
                "failed_jobs": 3,
                "avg_ms": 5000,
            },
        },
        background_jobs={
            "source": "background_result_timing_summary",
            "legacy_final_drain_result_count": 8,
            "combined_background_llm_jobs": 20,
            "total_jobs": 20,
            "jobs_submitted": 20,
            "jobs_attached_total": 20,
            "jobs_attached_pre_turn": 12,
            "jobs_attached_final": 8,
            "failed_jobs": 3,
            "timeout_job_count": 3,
            "missing_job_count": 0,
        },
        background_result_timing_summary={
            "jobs_submitted": 20,
            "jobs_attached_total": 20,
            "jobs_attached_pre_turn": 12,
            "jobs_attached_final": 8,
            "missing_job_count": 0,
        },
    )

    background_llm = result["background_llm"]
    assert background_llm["source"] == "reconciled_background_jobs"
    assert background_llm["legacy_final_drain_result_count"] == 8
    assert background_llm["combined_background_llm_jobs"] == 20
    assert background_llm["total_jobs"] == 20
    assert background_llm["jobs_submitted"] == 20
    assert background_llm["jobs_attached_pre_turn"] == 12
    assert background_llm["jobs_attached_final"] == 8
    assert background_llm["pre_turn_drain_accounted"] is True
    assert background_llm["failed_jobs"] == 3
    assert background_llm["timeout_job_count"] == 3
    # Existing timing fields should be preserved.
    assert background_llm["avg_ms"] == 5000