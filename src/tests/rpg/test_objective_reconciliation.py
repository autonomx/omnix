from app.rpg.objectives.handoff import apply_generic_quest_handoff
from app.rpg.objectives.reconciliation import reconcile_objective_progression_into_quests


def test_reconciliation_completes_stale_quest_progress_from_log():
    state = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "quest_id": "quest:witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:find_witness",
                            "summary": "Find the witness.",
                            "status": "active",
                            "completed": False,
                        },
                        {
                            "objective_id": "objective:report_to_bran",
                            "summary": "Report findings.",
                            "status": "active",
                            "completed": False,
                        },
                    ],
                }
            }
        },
        "objective_progression_log": [
            {"objective_id": "objective:find_witness", "matched": True, "completed": True},
            {"objective_id": "objective:report_to_bran", "matched": True, "completed": True},
        ],
    }

    result = reconcile_objective_progression_into_quests(state)

    assert result["changed"] is True
    quest = state["quest_progress"]["quests"]["quest:witness_search"]
    assert quest["status"] == "completed"
    assert quest["completed"] is True
    assert all(objective["completed"] for objective in quest["objectives"])


def test_reconciliation_then_handoff_creates_next_generic_quest():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:first_a",
                            "summary": "Find the clue.",
                            "status": "active",
                            "completed": False,
                        }
                    ],
                }
            }
        },
        "objective_progression_log": [
            {"objective_id": "objective:first_a", "matched": True, "completed": True}
        ],
        "known_leads": [{"name": "old bridge", "type": "location"}],
    }

    reconcile_objective_progression_into_quests(state)
    handoff = apply_generic_quest_handoff(state)

    assert handoff["changed"] is True
    quests = state["quest_progress"]["quests"]
    assert any(quest.get("source") == "generic_quest_handoff" for quest in quests.values())


def test_reconciliation_promotes_quest_log_state_to_quest_progress():
    state = {
        "quest_log_state": {
            "quests": {
                "quest:log_only": {
                    "title": "Log Only",
                    "status": "active",
                    "objectives": [
                        {
                            "objective_id": "objective:log_only",
                            "summary": "Inspect the shrine.",
                            "status": "active",
                            "completed": False,
                        }
                    ],
                }
            }
        },
        "objective_progression_log": [
            {"objective_id": "objective:log_only", "matched": True, "completed": True}
        ],
    }

    reconcile_objective_progression_into_quests(state)

    assert "quest_progress" in state
    quest = state["quest_progress"]["quests"]["quest:log_only"]
    assert quest["status"] == "completed"
    assert quest["objectives"][0]["completed"] is True