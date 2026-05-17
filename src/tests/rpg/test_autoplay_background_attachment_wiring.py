from tests.rpg.autoplay_llm_campaign import (
    _assert_background_presentation_attachment_wired,
    _build_background_presentation_attachment_summary,
)


def test_background_attachment_wiring_fails_when_completed_results_have_no_events():
    summary = {
        "background_presentation_completed_result_count": 2,
        "background_presentation_attachment_events": [],
        "background_presentation_attachment_summary": {},
    }

    try:
        _assert_background_presentation_attachment_wired(summary)
    except RuntimeError as exc:
        assert "background_presentation_attachment_not_wired" in str(exc)
    else:
        raise AssertionError("expected background attachment wiring failure")


def test_background_attachment_summary_counts_events_and_rows():
    summary = {
        "background_presentation_attachment_events": [
            {
                "attached": True,
                "reason": "attached_to_matching_turn",
                "phase": "final_background_drain",
            },
            {
                "attached": False,
                "reason": "identity_mismatch",
                "phase": "final_background_drain",
            },
        ],
        "orphaned_background_presentation_results": [
            {"reason": "identity_mismatch"}
        ],
    }

    transcript = [
        {"turn_index": 1, "presentation_status": "attached"},
        {"turn_index": 2, "presentation_status": "attached_repaired"},
        {"turn_index": 3, "presentation_status": "pending"},
    ]

    attachment_summary = _build_background_presentation_attachment_summary(
        summary,
        transcript,
    )

    assert attachment_summary["event_count"] == 2
    assert attachment_summary["attached_count"] == 1
    assert attachment_summary["rejected_count"] == 1
    assert attachment_summary["orphaned_count"] == 1
    assert attachment_summary["attached_row_count"] == 2
    assert attachment_summary["pending_count"] == 1
    assert attachment_summary["by_reason"]["attached_to_matching_turn"] == 1
    assert attachment_summary["by_reason"]["identity_mismatch"] == 1
