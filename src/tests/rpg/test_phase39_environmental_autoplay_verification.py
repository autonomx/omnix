from __future__ import annotations

from app.rpg.environmental_autoplay_verification import build_environmental_autoplay_verification
from app.rpg.report_surface_runtime import attach_report_surface_to_summary


def test_phase39_verifies_report_surface_environmental_coverage() -> None:
    summary = attach_report_surface_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "new_game": True,
                        "simulation_state": {
                            "location": {"id": "gate"},
                            "environment": {"weather": "fog", "sights": ["mist on the arch"]},
                        },
                    }
                },
                {
                    "turn_result": {
                        "simulation_state": {
                            "location": {"id": "gate", "ambient_activity": ["guards wave merchants through"]},
                            "environment": {"weather": "sun", "sights": ["bright stones"]},
                            "world": {"npcs": [{"name": "Bran", "location": "gate", "activity": "questions a courier"}]},
                        },
                    }
                },
            ]
        }
    )

    result = build_environmental_autoplay_verification(summary)

    assert result["ready"] is True
    assert result["environmental_panel_rows"] == 2
    assert result["environmental_narration_rows"] == 2
    assert result["carried_previous_scene_count"] == 1
    assert result["visible_activity_rows"] >= 1
    assert result["trigger_counts"]["weather_changed"] >= 1
    assert result["trigger_counts"]["changed_return_visit"] >= 1
    assert result["changed_field_counts"]["weather"] >= 1
    assert result["opportunity_counts"]["conversation_or_rumor"] >= 1


def test_phase39_flags_missing_transcript_rows() -> None:
    result = build_environmental_autoplay_verification({})

    assert result["ready"] is False
    assert result["issues"] == ["no_transcript_rows"]
