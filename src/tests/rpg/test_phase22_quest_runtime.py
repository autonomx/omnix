from __future__ import annotations

from app.rpg.quest_runtime import build_quest_runtime_report


def test_phase22_converts_lead_to_quest() -> None:
    report = build_quest_runtime_report(
        {
            "turn": 3,
            "leads": [
                {
                    "lead_id": "bandit-trail",
                    "summary": "Bandit Trail",
                    "clue": "Fresh bootprints",
                    "location_id": "quarry",
                    "npc_id": "bran",
                }
            ],
        }
    )

    assert report["ready"] is True
    assert report["converted_quests"][0]["quest_id"] == "bandit-trail"
    assert report["journal"]["suggested_actions"]


def test_phase22_deadline_statuses() -> None:
    report = build_quest_runtime_report(
        {
            "turn": 5,
            "quests": [{"quest_id": "q1", "title": "Find Bran", "status": "accepted"}],
            "deadlines": [{"quest_id": "q1", "due_turn": 4}],
        }
    )

    assert report["deadlines"][0]["status"] == "expired"
    assert report["expired_quest_ids"] == ["q1"]


def test_phase22_flags_deadline_for_unknown_quest() -> None:
    report = build_quest_runtime_report(
        {"turn": 1, "deadlines": [{"quest_id": "missing", "due_turn": 2}]}
    )

    assert report["ready"] is False
    assert "deadline_unknown_quest:missing" in report["issues"]
