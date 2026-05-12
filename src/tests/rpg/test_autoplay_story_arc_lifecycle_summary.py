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


def test_story_arc_lifecycle_summary_splits_original_and_seeded_followups():
    summary = _build_story_arc_lifecycle_summary(
        story_arcs={
            "arc:done": {
                "arc_id": "arc:done",
                "title": "Done",
                "status": "completed",
            },
            "arc:next": {
                "arc_id": "arc:next",
                "title": "Next",
                "status": "active",
                "current_stage": "seeded_followup",
                "source_hook_id": "hook:next",
            },
        },
        events=[
            {
                "type": "story_arc",
                "subtype": "arc_completed",
                "arc_id": "arc:done",
            }
        ],
    )

    assert summary["completed_count"] == 1
    assert summary["active_count"] == 1
    assert summary["original_active_count"] == 0
    assert summary["seeded_followup_active_count"] == 1
    assert summary["unresolved_original_arcs"] == []
    assert summary["active_followup_arcs"][0]["arc_id"] == "arc:next"


def test_story_arc_lifecycle_summary_classifies_progressed_seeded_followups():
    summary = _build_story_arc_lifecycle_summary(
        story_arcs={
            "arc:done": {
                "arc_id": "arc:done",
                "title": "Done",
                "status": "completed",
            },
            "arc:next": {
                "arc_id": "arc:next",
                "title": "Next",
                "status": "active",
                "current_stage": "chain_notices_missing_scouts",
                "seeded_followup": True,
                "source_hook_id": "hook:next",
                "progress_count": 1,
                "history": [
                    {"turn": 9, "type": "arc_seeded"},
                    {"turn": 12, "type": "followup_arc_progressed"},
                ],
            },
        },
        events=[
            {
                "type": "story_arc",
                "subtype": "arc_completed",
                "arc_id": "arc:done",
            }
        ],
    )

    assert summary["completed_count"] == 1
    assert summary["active_count"] == 1
    assert summary["original_active_count"] == 0
    assert summary["seeded_followup_active_count"] == 1
    assert summary["unresolved_original_arcs"] == []
    assert summary["active_followup_arcs"][0]["arc_id"] == "arc:next"