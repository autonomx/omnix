from tests.rpg.autoplay_llm_campaign import (
    _background_presentation_expected_attachment_count,
    _build_background_attachment_events_from_timing_summary,
    _assert_background_presentation_attachment_wired,
)


def test_expected_attachment_count_uses_existing_background_timing_summary():
    summary = {
        "background_result_timing_summary": {
            "jobs_attached_total": 100,
        },
        "background_jobs": {
            "combined_background_llm_jobs": 100,
        },
        "deferred_narration_trace_summary": {
            "ok_jobs": 100,
        },
    }

    assert _background_presentation_expected_attachment_count(summary) == 100


def test_background_attachment_wiring_fails_when_timing_says_attached_but_no_events():
    summary = {
        "background_result_timing_summary": {
            "jobs_attached_total": 100,
        },
        "background_presentation_attachment_events": [],
        "background_presentation_attachment_summary": {},
    }

    try:
        _assert_background_presentation_attachment_wired(summary)
    except RuntimeError as exc:
        assert "background_presentation_attachment_not_wired" in str(exc)
        assert "expected_count=100" in str(exc)
    else:
        raise AssertionError("expected background attachment wiring failure")


def test_build_legacy_attachment_events_from_timing_summary():
    summary = {
        "background_result_timing_summary": {
            "attachment_events": [
                {
                    "source_turn": 13,
                    "attach_turn": 16,
                    "lag_turns": 3,
                    "phase": "pre_turn",
                    "job_id": "job:13",
                }
            ]
        }
    }

    events = _build_background_attachment_events_from_timing_summary(summary)

    assert len(events) == 1
    assert events[0]["attached"] is True
    assert events[0]["source_turn"] == 13
    assert events[0]["attach_turn"] == 16
    assert events[0]["legacy_observed_only"] is True
    assert events[0]["turn_bound_verified"] is False
