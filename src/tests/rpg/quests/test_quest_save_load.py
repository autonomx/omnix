import json

from app.rpg.quests.state import complete_objective, normalize_quest_state, start_quest


def test_quest_state_json_roundtrip():
    simulation_state = {}
    start_quest(
        simulation_state,
        "quest:rat_cellar",
        stage="started",
        objectives={"talk_to_bran": {"description": "Talk to Bran."}},
    )
    complete_objective(simulation_state, "quest:rat_cellar", "talk_to_bran", turn_index=2)

    encoded = json.dumps(simulation_state["quest_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_quest_state(decoded)

    quest = normalized["quests"]["quest:rat_cellar"]
    assert quest["stage"] == "started"
    assert quest["objectives"]["talk_to_bran"]["status"] == "completed"