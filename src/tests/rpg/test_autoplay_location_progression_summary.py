from tests.rpg.autoplay_llm_campaign import (
    _apply_scenario_progression_location_bridge,
    _build_location_progression_summary,
    _build_canonical_progress_quality_summary,
)


def test_location_progression_summary_reads_progress_timeline_location_change():
    transcript = [
        {"turn_index": 1, "player_action": "I ask Bran about the road."},
        {"turn_index": 2, "player_action": "I travel to the old mill."},
    ]
    final_summary = {
        "progress_timeline_summary": {
            "turns": 2,
            "meaningful_progress_turns": 2,
            "meaningful_progress_rate": 1.0,
            "location_changes": 1,
            "timeline": [
                {"turn_index": 1, "location": "scene:rusty_flagon", "location_changed": False},
                {"turn_index": 2, "location": "location:old_mill", "location_changed": True},
            ],
        }
    }

    summary = _build_location_progression_summary(transcript, final_summary=final_summary)

    assert summary["ok"] is True
    assert summary["visited_location_count"] == 2
    assert summary["travel_turn_count"] == 1


def test_location_bridge_marks_travel_action_as_location_progression():
    row = {
        "turn_index": 23,
        "player_action": "I travel to the old mill ruins to follow the marked coin lead.",
        "location": "scene:rusty_flagon",
    }

    _apply_scenario_progression_location_bridge(row)

    assert row["location_changed"] is True
    assert row["current_location"] == "location:old_mill"
    assert row["travel_result"]["ok"] is True
    assert row["meaningful_progress"] is True


def test_canonical_progress_prefers_progress_timeline_summary():
    final_summary = {
        "progress_timeline_summary": {
            "turns": 100,
            "meaningful_progress_turns": 100,
            "meaningful_progress_rate": 1.0,
            "location_changes": 1,
            "story_beat_turns": 100,
            "npc_signal_turns": 85,
            "quest_progress_turns": 11,
            "journal_entry_turns": 6,
        },
        "health": {
            "metrics": {
                "progress_quality": {
                    "turn_count": 100,
                    "meaningful_turns": 1,
                    "meaningful_progress_rate": 0.01,
                    "no_change_turns": 97,
                }
            }
        },
    }

    summary = _build_canonical_progress_quality_summary(
        transcript=[],
        existing_progress={},
        strict_progress={},
        final_summary=final_summary,
    )

    assert summary["source"] == "progress_timeline_summary"
    assert summary["meaningful_progress_rate"] == 1.0
    assert summary["no_change_turns"] == 0