from tests.rpg.autoplay.progress import (
    classify_progress_delta,
    no_progress_streak,
    state_digest,
)


def test_state_digest_changes_when_selected_state_changes():
    before = {"story_arc_state": {"arcs": {}}}
    after = {"story_arc_state": {"arcs": {"arc:x": {"stage": "start"}}}}

    assert state_digest(before)["hash"] != state_digest(after)["hash"]


def test_classify_progress_delta_detects_milestone_completion():
    before = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "active"}
                    ]
                }
            }
        }
    }
    after = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "completed"}
                    ]
                }
            }
        }
    }

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert delta["changed"] is True
    assert "milestone_completed" in delta["categories"]
    assert delta["completed_milestones"] == ["milestone:x"]


def test_no_progress_streak_counts_trailing_no_progress_turns():
    transcript = [
        {"progress_delta": {"changed": True, "categories": ["state_changed"]}},
        {"progress_delta": {"changed": False, "categories": []}},
        {"progress_delta": {"changed": False, "categories": []}},
    ]

    assert no_progress_streak(transcript) == 2