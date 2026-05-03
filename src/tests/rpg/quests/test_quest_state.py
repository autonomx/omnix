from app.rpg.quests.state import (
    complete_objective,
    get_quest,
    set_quest_stage,
    start_quest,
)


def test_start_quest_sets_active_stage_and_objectives():
    simulation_state = {}
    result = start_quest(
        simulation_state,
        "quest:rat_cellar",
        title="Rats in the Cellar",
        stage="started",
        objectives={
            "talk_to_bran": {"description": "Talk to Bran."},
        },
        turn_index=1,
    )

    quest = get_quest(simulation_state, "quest:rat_cellar")
    assert result["ok"] is True
    assert quest["status"] == "active"
    assert quest["stage"] == "started"
    assert quest["objectives"]["talk_to_bran"]["status"] == "open"


def test_complete_objective_marks_completed():
    simulation_state = {}
    start_quest(
        simulation_state,
        "quest:rat_cellar",
        objectives={"talk_to_bran": {"description": "Talk to Bran."}},
    )

    result = complete_objective(
        simulation_state,
        "quest:rat_cellar",
        "talk_to_bran",
        turn_index=2,
    )

    assert result["ok"] is True
    assert result["objective"]["status"] == "completed"
    assert result["objective"]["completed_turn"] == 2


def test_set_quest_stage_can_complete():
    simulation_state = {}
    start_quest(simulation_state, "quest:rat_cellar")
    result = set_quest_stage(
        simulation_state,
        "quest:rat_cellar",
        "completed",
        status="completed",
        turn_index=3,
    )

    assert result["ok"] is True
    assert result["quest"]["status"] == "completed"
    assert result["quest"]["completed_turn"] == 3