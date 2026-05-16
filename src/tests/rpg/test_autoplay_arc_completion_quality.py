from tests.rpg.autoplay_llm_campaign import _build_arc_completion_quality_summary


def test_arc_completion_quality_warns_when_only_failed_arcs_resolve():
    summary = {
        "story_arc_lifecycle_summary": {
            "completed_count": 0,
            "failed_count": 2,
            "resolved_count": 2,
        },
        "story_arc_aftermath_summary": {
            "aftermath_event_count": 20,
        },
        "followup_arc_resolution_summary": {
            "resolved_or_escalated_count": 1,
        },
    }

    quality = _build_arc_completion_quality_summary(summary)

    assert quality["ok"] is True
    assert quality["product_quality_ok"] is False
    assert "story_arcs_resolved_only_by_failure" in quality["warnings"]
    assert "no_successful_story_arc_completion" in quality["warnings"]


def test_arc_completion_quality_passes_when_arc_completed():
    summary = {
        "story_arc_lifecycle_summary": {
            "completed_count": 1,
            "failed_count": 0,
            "resolved_count": 1,
        }
    }

    quality = _build_arc_completion_quality_summary(summary)

    assert quality["ok"] is True
    assert quality["product_quality_ok"] is True
    assert quality["warnings"] == []
