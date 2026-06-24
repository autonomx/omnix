from __future__ import annotations

from app.rpg.gameplay_closure_runtime import build_gameplay_closure_report


def test_phase27_closure_builds_next_actions() -> None:
    report = build_gameplay_closure_report(
        {
            "simulation_state": {
                "world": {},
                "player": {"location_id": "start"},
                "inventory": {},
                "quests": {},
                "npcs": {},
                "map": {
                    "locations": {"start": {"status": "expanded"}, "road": {"status": "expanded"}},
                    "routes": [{"from_id": "start", "to_id": "road", "status": "open"}],
                },
            },
            "quests": [{"quest_id": "q1", "title": "Trail", "status": "accepted", "location_ids": ["road"]}],
            "npc_ids": ["bran"],
            "social_thread": {"thread_id": "t1", "kind": "directed", "participants": ["bran"]},
            "speak_requests": [{"npc_id": "bran", "directly_addressed": True}],
        }
    )

    assert report["ready"] is True
    assert report["suggested_next_actions"]
    assert "npc_memory_summaries" in report["effects"]


def test_phase27_closure_flags_missing_suggestions() -> None:
    report = build_gameplay_closure_report({})

    assert report["ready"] is False
    assert "missing_suggested_next_actions" in report["issues"]
