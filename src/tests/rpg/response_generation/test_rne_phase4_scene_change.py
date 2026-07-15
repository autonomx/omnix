from __future__ import annotations

from app.rpg.narrative_engine import BeatPurpose, detect_scene_changes


def test_new_game_requires_scene_establishment() -> None:
    report = detect_scene_changes(None, {"location_id": "rusty_flagon", "new_game": True})
    assert report.scene_refresh_required is True
    assert [change.kind for change in report.changes] == ["new_game"]
    assert BeatPurpose.SCENE_ESTABLISHMENT in report.required_beat_purposes
    assert BeatPurpose.ENVIRONMENTAL_CHANGE in report.required_beat_purposes


def test_location_and_weather_changes_create_required_beats() -> None:
    report = detect_scene_changes(
        {"location_id": "road", "weather": "clear", "turn_index": 4},
        {"location_id": "quarry", "weather": "rain", "turn_index": 5},
    )
    assert [change.kind for change in report.changes] == ["location_changed", "weather_changed"]
    assert report.required_beat_purposes == (
        BeatPurpose.SCENE_ESTABLISHMENT,
        BeatPurpose.ENVIRONMENTAL_CHANGE,
    )


def test_unchanged_scene_does_not_repeat_introduction() -> None:
    report = detect_scene_changes(
        {"location_id": "rusty_flagon", "weather": "rain"},
        {"location_id": "rusty_flagon", "weather": "rain"},
    )
    assert report.scene_refresh_required is False
    assert report.required_beat_purposes == ()


def test_changed_return_visit_is_detected_without_location_change() -> None:
    report = detect_scene_changes(
        {"location_id": "rusty_flagon", "location_revision": 1, "turn_index": 10},
        {
            "location_id": "rusty_flagon",
            "location_revision": 2,
            "visited_before": True,
            "turn_index": 20,
        },
    )
    assert [change.kind for change in report.changes] == ["changed_return_visit"]
    assert BeatPurpose.SCENE_ESTABLISHMENT in report.required_beat_purposes
