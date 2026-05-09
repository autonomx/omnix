from app.rpg.objectives.progression_rules import (
    apply_objective_progression_rules,
    build_progression_event,
    objective_progress_matches_event,
)


def test_declarative_rule_completes_missing_scout_objective():
    objective = {
        "objective_id": "objective:find_scout",
        "summary": "Find the missing scout.",
        "completion_rules": [
            {
                "semantic_actions": ["ask", "inspect", "travel"],
                "topics": ["scout"],
            }
        ],
    }
    event = build_progression_event(
        player_action="I inspect the forest trail for signs of the missing scout.",
        state={},
    )
    assert objective_progress_matches_event(objective, event)

def test_apply_progression_rules_completes_generic_quest_objective():
    state = {
        "quest_log_state": {
            "quests": {
                "quest:scout": {
                    "title": "Missing Scout",
                    "objectives": [
                        {
                            "objective_id": "objective:find_scout",
                            "summary": "Find the missing scout.",
                            "completion_rules": [
                                {"semantic_actions": ["inspect"], "topics": ["scout", "trail"]}
                            ],
                        }
                    ],
                }
            }
        }
    }
    result = apply_objective_progression_rules(
        state,
        player_action="I inspect the forest trail for signs of the missing scout.",
    )
    assert result["changed"] is True
    objective = state["quest_log_state"]["quests"]["quest:scout"]["objectives"][0]
    assert objective["completed"] is True
    assert state["quest_log_state"]["quests"]["quest:scout"]["status"] == "completed"

def test_progression_rules_do_not_need_bran_or_witness_terms():
    state = {
        "quest_log_state": {
            "quests": {
                "quest:relic": {
                    "title": "Stolen Relic",
                    "objectives": [
                        {
                            "objective_id": "objective:recover_relic",
                            "summary": "Recover the stolen relic from the crypt.",
                            "objective_type": "recover",
                            "subject": "stolen relic",
                        }
                    ],
                }
            }
        }
    }
    result = apply_objective_progression_rules(
        state,
        player_action="I search the crypt for the stolen relic and secure it if present.",
    )
    assert result["changed"] is True


def test_progression_rules_record_partial_progress_for_matching_action():
    state = {
        "quest_log_state": {
            "quests": {
                "quest:scout": {
                    "title": "Missing Scout",
                    "objectives": [
                        {
                            "objective_id": "objective:find_scout",
                            "summary": "Find the missing scout.",
                            "objective_type": "find",
                            "subject": "missing scout",
                        }
                    ],
                }
            }
        }
    }

    result = apply_objective_progression_rules(
        state,
        player_action="I ask Captain Arlen who last saw the missing scout and where I should inspect next.",
    )

    assert result["changed"] is True
    assert state["objective_progression_log"]
    assert result["progressed_objectives"] or result["completed_objectives"]
