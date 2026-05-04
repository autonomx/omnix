import json

from app.rpg.quest_log.runtime import pin_objective
from app.rpg.quest_log.state import normalize_quest_log_state
from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc


def test_quest_log_state_json_roundtrip():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(simulation_state, arc_id="arc:x", milestone_id="milestone:x", title="X")
    pin_objective(simulation_state, "milestone:x")

    encoded = json.dumps(simulation_state["quest_log_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_quest_log_state(decoded)

    assert normalized["pinned_objective_ids"] == ["milestone:x"]


def test_quest_log_pinned_objectives_are_bounded():
    raw = {"pinned_objective_ids": [f"milestone:{i}" for i in range(30)]}

    normalized = normalize_quest_log_state(raw)

    assert len(normalized["pinned_objective_ids"]) == 10