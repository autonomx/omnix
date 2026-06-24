from __future__ import annotations

from app.rpg.environmental_activity_runtime import build_environmental_activity_report
from app.rpg.environmental_narration_runtime import build_environmental_narration_report


def test_phase37_activity_reads_world_npc_and_event_schedules() -> None:
    report = build_environmental_activity_report(
        {
            "simulation_state": {
                "location": {"id": "market", "current_activity": ["crowds press toward the fountain"]},
                "environment": {"sights": ["wet banners"]},
                "world": {
                    "npcs": [
                        {"name": "Bran", "location": "market", "activity": "argues with a spice courier"},
                        {"name": "Elara", "location": "harbor", "activity": "counts crates"},
                    ],
                    "scheduled_events": [
                        {"id": "bell", "location_id": "market", "description": "alarm bells ring over the square"}
                    ],
                },
            }
        }
    )

    texts = [item["text"] for item in report["visible_activity"]]
    assert "crowds press toward the fountain" in texts
    assert "Bran: argues with a spice courier" in texts
    assert "Elara: counts crates" not in texts
    assert "alarm bells ring over the square" in texts
    assert report["intensity"] == "high"
    assert "conversation_or_rumor" in report["opportunities"]
    assert "local_event_hook" in report["opportunities"]


def test_phase37_narration_contract_receives_scheduled_activity() -> None:
    report = build_environmental_narration_report(
        {
            "new_game": True,
            "simulation_state": {
                "location": {"id": "tavern", "ambient_activity": ["patrons trade rumors"]},
                "environment": {"sights": ["lantern smoke"]},
                "world": {"npcs": [{"name": "Bran", "location": "tavern", "task": "serves stew"}]},
            },
        }
    )

    activity = report["scene_introduction_contract"]["living_activity"]
    assert activity["actor_groups"] == ("population", "npc")
    assert any(item["text"] == "Bran: serves stew" for item in activity["visible_activity"])
