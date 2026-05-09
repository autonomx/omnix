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


def test_progression_rules_persist_evaluation_log_even_when_no_match():
    from app.rpg.objectives.progression_rules import apply_objective_progression_rules

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
        player_action="I play a lute in the corner.",
    )

    assert "objective_progression_log" in state
    assert state["objective_progression_log"]
    assert state["objective_progression_log"][-1]["matched"] is False
    assert result["event"]["semantic_action"]


def test_objective_progression_summary_requires_matched_rows_for_ok():
    from tests.rpg.autoplay_llm_campaign import _objective_progression_summary_from_state

    state = {
        "objective_progression_log": [
            {"matched": False, "summary": "evaluated but no match"},
            {"matched": False, "summary": "evaluated but no match"},
        ]
    }

    summary = _objective_progression_summary_from_state(state)

    assert summary["evaluated_count"] == 2
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["ok"] is False


def test_objective_progression_summary_ok_with_partial_or_completed_match():
    from tests.rpg.autoplay_llm_campaign import _objective_progression_summary_from_state

    state = {
        "objective_progression_log": [
            {"matched": False, "summary": "evaluated but no match"},
            {"matched": True, "partial": True, "summary": "objective progressed"},
        ]
    }

    summary = _objective_progression_summary_from_state(state)

    assert summary["matched_count"] == 1
    assert summary["partial_count"] == 1
    assert summary["ok"] is True
