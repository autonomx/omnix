from __future__ import annotations

from app.rpg.env_scene_trace import attach, carry
from app.rpg.report_surface_runtime import attach_report_surface_to_summary


def test_phase36_carry_adds_prior_scene_when_missing() -> None:
    row = carry({"turn_result": {"location": {"id": "gate"}}}, {"location": "gate", "weather": "fog"})

    assert row["turn_result"]["previous_scene"]["weather"] == "fog"
    assert row["env_scene_trace"]["prior_carried"] is True


def test_phase36_report_surface_uses_previous_row_snapshot() -> None:
    summary = attach_report_surface_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "new_game": True,
                        "location": {"id": "gate"},
                        "environment": {"weather": "fog", "sights": ["mist on the arch"]},
                    }
                },
                {
                    "turn_result": {
                        "location": {"id": "gate"},
                        "environment": {"weather": "sun", "sights": ["bright stones"]},
                    }
                },
            ]
        }
    )

    second = summary["transcript_rows"][1]
    assert second["turn_result"]["previous_scene"]["weather"] == "fog"
    assert second["env_scene_trace"]["prior_carried"] is True
    env = second["report_surface"]["sections"]["environmental_narration"]
    assert "weather_changed" in env["triggers"]
    assert "changed_return_visit" in env["triggers"]


def test_phase36_attach_counts_carried_rows() -> None:
    summary = attach(
        {
            "transcript_rows": [
                {"environmental_narration": {"state_memory": {"current_snapshot": {"location": "road"}}}},
                {"turn_result": {"location": {"id": "road"}}},
            ]
        }
    )

    assert summary["env_scene_trace"]["carried_count"] == 1
