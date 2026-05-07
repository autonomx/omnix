from tests.rpg.autoplay_llm_campaign import (
    _new_background_result_timing_tracker,
    _summarize_background_result_timing,
    _track_background_attach,
    _track_background_submit,
)


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