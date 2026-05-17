from tests.rpg.autoplay_llm_campaign import _assert_turn_bound_attachment_verified


def test_turn_bound_attachment_verified_fails_on_legacy_observed_only():
    summary = {
        "background_result_timing_summary": {"jobs_attached_total": 1},
        "background_jobs": {"combined_background_llm_jobs": 1},
        "deferred_narration_trace_summary": {"ok_jobs": 1},
        "background_presentation_attachment_summary": {
            "event_count": 1,
            "turn_bound_verified_count": 0,
            "legacy_observed_count": 1,
            "rejected_count": 0,
            "orphaned_count": 0,
            "turn_bound_attachment_verified": False,
        },
    }

    try:
        _assert_turn_bound_attachment_verified(summary)
    except RuntimeError as exc:
        assert "background_presentation_not_turn_bound_verified" in str(exc)
    else:
        raise AssertionError("expected turn-bound verification failure")
