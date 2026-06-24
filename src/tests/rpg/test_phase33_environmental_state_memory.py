from __future__ import annotations

from app.rpg.environmental_narration_runtime import (
    attach_environmental_narration_to_summary,
    build_environmental_narration_report,
    build_environmental_state_memory,
)


def test_phase33_return_visit_memory_marks_changed_context() -> None:
    report = build_environmental_narration_report(
        {
            "previous_scene": {
                "location": "market",
                "weather": "clear",
                "population_activity": ["quiet stalls"],
                "sights": ["empty square"],
            },
            "simulation_state": {
                "location": {"id": "market", "region_id": "old-town"},
                "environment": {
                    "weather": "rain",
                    "sights": ["lanterns in the puddles"],
                    "population_activity": ["vendors pulling canvas over carts"],
                },
            },
        }
    )

    assert "changed_return_visit" in report["triggers"]
    memory = report["state_memory"]
    assert memory["location_seen_before"] is True
    changed = {item["field"]: item for item in memory["changed_fields"]}
    assert changed["weather"]["before"] == "clear"
    assert changed["weather"]["after"] == "rain"
    contract = report["scene_introduction_contract"]
    assert contract["state_memory"] == memory
    assert any(item["field"] == "population_activity" for item in contract["changed_context"])


def test_phase33_state_memory_normalizes_perceptual_changes() -> None:
    memory = build_environmental_state_memory(
        {
            "previous_environment": {"location": "road", "sounds": ["wind"]},
            "simulation_state": {
                "location": {"id": "road"},
                "environment": {"sounds": ["distant bells"], "sights": ["dust on the stones"]},
            },
        }
    )

    perceptual = {item["field"]: item for item in memory["perceptual_changes"]}
    assert perceptual["sounds"]["before"] == ("wind",)
    assert perceptual["sounds"]["after"] == ("distant bells",)
    assert perceptual["sights"]["after"] == ("dust on the stones",)


def test_phase33_summary_counts_environmental_memory_fields() -> None:
    summary = attach_environmental_narration_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "previous_scene": {"location": "gate", "weather": "fog"},
                        "simulation_state": {
                            "location": {"id": "gate"},
                            "environment": {"weather": "sun", "sights": ["open road"]},
                        },
                    }
                }
            ]
        }
    )

    assert summary["environmental_narration"]["memory_change_counts"] == {"weather": 1}
