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


def test_classify_progress_delta_detects_location_change():
    before = {"scene": {"location": "Tavern"}}
    after = {"scene": {"location": "Road"}}

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert "location_changed" in delta["categories"]


def test_classify_progress_delta_detects_story_event_queue_added():
    before = {"story_event_queue_state": {"queue": []}}
    after = {"story_event_queue_state": {"queue": [{"event_id": "event:x"}]}}

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert "story_event_queued" in delta["categories"]


def test_classify_progress_delta_detects_combat_started():
    before = {"combat_state": {"active": False}}
    after = {"combat_state": {"active": True}}

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert "combat_started" in delta["categories"]


def test_classify_progress_delta_detects_witness_hook_meaningful_progress():
    before = {
        "story_arc_state": {
            "arcs": {
                "arc:witness_search": {"stage": "rumors"}
            }
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "active"}
                    ]
                }
            }
        },
        "campaign_journal_state": {"entries": []},
        "story_event_queue_state": {"queue": []},
    }
    after = {
        "story_arc_state": {
            "arcs": {
                "arc:witness_search": {"stage": "witness_found"}
            }
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "completed"}
                    ]
                }
            }
        },
        "campaign_journal_state": {
            "entries": [{"entry_id": "journal:witness:found"}]
        },
        "story_event_queue_state": {
            "queue": [{"event_id": "event:witness:found"}]
        },
    }

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert "milestone_completed" in delta["categories"]
    assert "objective_completed" in delta["categories"]
    assert "arc_stage_changed" in delta["categories"]
    assert "journal_entry_added" in delta["categories"]
    assert "story_event_queued" in delta["categories"]