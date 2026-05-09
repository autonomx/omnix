from app.rpg.objectives.affordances import (
    build_objective_affordances_for_state,
    command_has_planner_language,
    infer_objective_type,
    objective_affordance_actions,
)


def test_affordances_for_find_missing_scout_are_generic_and_executable():
    objective = {
        "objective_id": "objective:find_scout",
        "summary": "Find the missing scout.",
        "objective_type": "find",
        "subject": "missing scout",
        "known_leads": ["watchtower", "forest trail"],
        "quest_giver": "Captain Arlen",
    }
    actions = objective_affordance_actions(objective, {"nearby_npcs": [{"name": "Captain Arlen"}]})
    commands = [row["command"] for row in actions]
    assert any("I ask Captain Arlen" in command for command in commands)
    assert any("I inspect watchtower" in command or "I inspect forest trail" in command for command in commands)
    assert all(command.startswith("I ") for command in commands)
    assert not any("Bran" in command or "cloaked traveler" in command for command in commands)

def test_affordances_for_recover_relic_are_not_scenario_specific():
    objective = {
        "summary": "Recover the stolen relic from the crypt.",
        "objective_type": "recover",
        "subject": "stolen relic",
        "known_leads": ["crypt"],
        "quest_giver": "Priestess Mara",
    }
    actions = objective_affordance_actions(objective, {})
    commands = " ".join(row["command"] for row in actions)
    assert "stolen relic" in commands
    assert "crypt" in commands
    assert "Bran" not in commands

def test_build_objective_affordances_from_state_reads_quest_log():
    state = {
        "quest_log_state": {
            "quests": {
                "quest:relic": {
                    "title": "Stolen Relic",
                    "quest_giver": "Priestess Mara",
                    "objectives": [
                        {
                            "objective_id": "objective:recover_relic",
                            "summary": "Recover the stolen relic from the crypt.",
                            "objective_type": "recover",
                            "subject": "stolen relic",
                            "known_leads": ["crypt"],
                        }
                    ],
                }
            }
        }
    }
    actions = build_objective_affordances_for_state(state)
    assert actions
    assert any("stolen relic" in row["command"] for row in actions)


def test_affordance_commands_do_not_use_planner_language():
    objective = {
        "objective_id": "objective:find_scout",
        "summary": "Find the missing scout.",
        "objective_type": "find",
        "subject": "missing scout",
        "known_leads": ["forest trail"],
        "quest_giver": "Captain Arlen",
    }
    actions = objective_affordance_actions(objective, {})
    assert actions
    assert all(not command_has_planner_language(row["command"]) for row in actions)
    assert not any("what concrete lead I should act on next" in row["command"] for row in actions)


def test_build_objective_affordances_ignores_objective_completed_only_in_progression_log():
    state = {
        "quest_progress": {
            "quests": {
                "quest:witness": {
                    "title": "Witness",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:find_witness",
                            "summary": "Find the witness.",
                            "objective_type": "find",
                            "subject": "witness",
                            "known_leads": ["alley"],
                            "completed": False,
                            "status": "active",
                        }
                    ],
                }
            }
        },
        "objective_progression_log": [
            {"objective_id": "objective:find_witness", "matched": True, "completed": True}
        ],
    }

    actions = build_objective_affordances_for_state(state)

    assert actions == []
