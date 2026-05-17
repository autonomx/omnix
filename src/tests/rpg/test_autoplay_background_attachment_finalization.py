from tests.rpg.autoplay_llm_campaign import (
    _assert_background_presentation_attachment_wired,
    _finalize_background_presentation_attachment_tracking,
)


def test_finalize_background_attachment_tracking_builds_legacy_events_before_assert():
    summary = {
        "background_result_timing_summary": {
            "jobs_attached_total": 2,
            "attachment_events": [
                {
                    "source_turn": 1,
                    "attach_turn": 3,
                    "lag_turns": 2,
                    "phase": "pre_turn",
                    "job_id": "job:1",
                },
                {
                    "source_turn": 2,
                    "attach_turn": 4,
                    "lag_turns": 2,
                    "phase": "final",
                    "job_id": "job:2",
                },
            ],
        },
        "background_jobs": {
            "combined_background_llm_jobs": 2,
        },
        "deferred_narration_trace_summary": {
            "ok_jobs": 2,
        },
        "background_presentation_attachment_events": [],
        "orphaned_background_presentation_results": [],
    }

    transcript = [
        {"turn_index": 1, "presentation_status": "pending"},
        {"turn_index": 2, "presentation_status": "pending"},
    ]

    finalized = _finalize_background_presentation_attachment_tracking(
        summary,
        transcript,
    )

    assert len(finalized["background_presentation_attachment_events"]) == 2
    assert finalized["background_presentation_attachment_summary"]["event_count"] == 2
    assert finalized["background_presentation_attachment_summary"]["legacy_observed_count"] == 2
    assert finalized["background_presentation_attachment_summary"]["turn_bound_verified_count"] == 0
    assert finalized["background_presentation_attachment_summary"]["turn_bound_attachment_verified"] is False

    _assert_background_presentation_attachment_wired(finalized)
