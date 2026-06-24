from __future__ import annotations

from app.rpg.environmental_activity_runtime import (
    attach_environmental_activity_to_summary,
    build_environmental_activity_report,
)
from app.rpg.environmental_narration_runtime import build_environmental_narration_report


def test_phase34_activity_report_surfaces_visible_living_activity() -> None:
    report = build_environmental_activity_report(
        {
            "simulation_state": {
                "location": {"id": "market", "faction_presence": ["watch patrol"]},
                "environment": {
                    "time_of_day": "dusk",
                    "population_activity": ["vendors closing stalls"],
                },
                "world": {"active_events": ["bell ringing over the square"]},
            },
            "nearby_npc_activity": ["Bran argues with a courier"],
        }
    )

    assert report["ready"] is True
    assert report["intensity"] == "high"
    assert report["actor_groups"] == ("population", "npc", "faction")
    assert "conversation_or_rumor" in report["opportunities"]
    assert "local_event_hook" in report["opportunities"]
    assert {item["kind"] for item in report["visible_activity"]} >= {"population", "npc", "event"}


def test_phase34_narration_contract_embeds_living_activity() -> None:
    report = build_environmental_narration_report(
        {
            "new_game": True,
            "location": {"id": "tavern"},
            "environment": {
                "sights": ["lantern smoke"],
                "population_activity": ["patrons speaking in low voices"],
            },
        }
    )

    activity = report["living_activity"]
    assert activity["intensity"] == "medium"
    assert report["scene_introduction_contract"]["living_activity"] == activity


def test_phase34_activity_summary_counts_opportunities() -> None:
    summary = attach_environmental_activity_to_summary(
        {
            "transcript_rows": [
                {
                    "turn_result": {
                        "location": {"id": "road"},
                        "nearby_npc_activity": ["a scout watches the crossroads"],
                    }
                }
            ]
        }
    )

    assert summary["environmental_activity"]["intensity_counts"] == {"medium": 1}
    assert summary["environmental_activity"]["opportunity_counts"] == {"conversation_or_rumor": 1}
