from __future__ import annotations

from app.rpg.environmental_narration_runtime import build_environmental_narration_report


def test_phase28_new_location_builds_scene_contract() -> None:
    report = build_environmental_narration_report(
        {
            "previous_scene": {"location": "tavern", "weather": "clear"},
            "simulation_state": {
                "location": {"id": "market", "region_id": "old-town", "landmarks": ["clock tower"]},
                "environment": {
                    "time_of_day": "morning",
                    "weather": "rain",
                    "sights": ["wet awnings"],
                    "sounds": ["cart wheels"],
                    "smells": ["bread smoke"],
                    "physical_feel": ["cold drizzle"],
                    "emotional_tone": "uneasy",
                },
            },
        }
    )

    assert report["should_generate"] is True
    assert "location_changed" in report["triggers"]
    contract = report["scene_introduction_contract"]
    assert contract["format"]["atmospheric_description"] == "1-2 paragraphs"
    assert contract["sensory_inputs"]["sounds"] == ("cart wheels",)


def test_phase28_changed_return_visit_trigger() -> None:
    report = build_environmental_narration_report(
        {
            "previous_scene": {"location": "village"},
            "meaningful_location_change": True,
            "simulation_state": {
                "location": {"id": "village"},
                "environment": {"sights": ["soldiers at the well"]},
            },
        }
    )

    assert "changed_return_visit" in report["triggers"]
    assert report["ready"] is True


def test_phase28_flags_missing_trigger_and_context() -> None:
    report = build_environmental_narration_report({})

    assert report["ready"] is False
    assert "no_scene_intro_trigger" in report["issues"]
    assert "missing_place_context" in report["issues"]
