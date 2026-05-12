from tests.rpg.autoplay_llm_campaign import _build_story_arc_lifecycle_summary


def test_story_arc_lifecycle_summary_counts_statuses():
    summary = _build_story_arc_lifecycle_summary(
        story_arcs={
            "arc:a": {
                "arc_id": "arc:a",
                "title": "A",
                "status": "completed",
            },
            "arc:b": {
                "arc_id": "arc:b",
                "title": "B",
                "status": "active",
            },
        },
        events=[
            {
                "type": "story_arc",
                "subtype": "arc_completed",
                "arc_id": "arc:a",
            }
        ],
    )

    assert summary["ok"] is True
    assert summary["completed_count"] == 1
    assert summary["active_count"] == 1
    assert summary["status_counts"]["completed"] == 1