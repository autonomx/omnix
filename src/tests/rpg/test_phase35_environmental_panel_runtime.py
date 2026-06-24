from __future__ import annotations

from app.rpg.environmental_panel_runtime import (
    attach_environmental_panel_to_summary,
    build_environmental_panel_report,
)
from app.rpg.report_surface_runtime import attach_report_surface_to_summary


def test_phase35_panel_surfaces_memory_and_activity() -> None:
    panel = build_environmental_panel_report(
        {
            "previous_scene": {"location": "market", "weather": "clear", "sights": ["empty square"]},
            "simulation_state": {
                "location": {"id": "market"},
                "environment": {
                    "weather": "rain",
                    "sights": ["awnings sagging with rain"],
                    "population_activity": ["vendors dragging crates under cover"],
                },
            },
        }
    )

    assert panel["ready"] is True
    assert "changed" in panel["badges"]
    assert "weather" in panel["changed_fields"]
    assert "sights" in panel["perceptual_fields"]
    assert panel["visible_activity"][0]["kind"] == "population"
    assert "conversation_or_rumor" in panel["opportunities"]
    assert any(str(cue).startswith("Changed:") for cue in panel["panel_cues"])


def test_phase35_report_surface_exposes_environmental_panel_section() -> None:
    result = attach_report_surface_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "new_game": True,
                        "location": {"id": "road"},
                        "environment": {
                            "sights": ["mist"],
                            "population_activity": ["travelers gather near the milestone"],
                        },
                    }
                }
            ]
        }
    )

    sections = result["transcript_rows"][0]["report_surface"]["sections"]
    assert sections["environmental_panel"]["title"] == "Environmental scene"
    assert "environmental_panel" in result["report_surface"]["sections"]


def test_phase35_panel_summary_counts_fields_and_opportunities() -> None:
    summary = attach_environmental_panel_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "previous_scene": {"location": "gate", "weather": "fog"},
                        "simulation_state": {
                            "location": {"id": "gate"},
                            "environment": {
                                "weather": "sun",
                                "sights": ["open road"],
                                "population_activity": ["guards wave merchants through"],
                            },
                        },
                    }
                }
            ]
        }
    )

    panel = summary["environmental_panel"]
    assert panel["changed_field_counts"] == {"weather": 1}
    assert panel["opportunity_counts"] == {"conversation_or_rumor": 1}
