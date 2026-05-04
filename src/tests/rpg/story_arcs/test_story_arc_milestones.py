import json

from app.rpg.story_arcs.milestones import (
    add_story_arc_milestone,
    build_story_objective_projection,
    complete_story_arc_milestone,
    get_story_arc_milestone,
    list_story_arc_milestones,
    normalize_story_arc_milestone_state,
)
from app.rpg.story_arcs.state import start_story_arc


def test_add_story_arc_milestone_creates_active_objective():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")

    result = add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:x",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
        turn_index=1,
    )
    projection = build_story_objective_projection(simulation_state)

    assert result["ok"] is True
    assert result["reason"] == "added"
    assert projection["active_objectives"][0]["objective_text"] == "Find the witness near the tavern."


def test_complete_story_arc_milestone_is_idempotent():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:x",
        title="Find the witness",
    )

    first = complete_story_arc_milestone(simulation_state, "milestone:x", turn_index=2)
    second = complete_story_arc_milestone(simulation_state, "milestone:x", turn_index=3)

    assert first["ok"] is True
    assert first["reason"] == "completed"
    assert second["ok"] is True
    assert second["reason"] == "already_completed"
    assert get_story_arc_milestone(simulation_state, "milestone:x")["status"] == "completed"


def test_list_story_arc_milestones_filters_status():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(simulation_state, arc_id="arc:x", milestone_id="milestone:a", title="A")
    add_story_arc_milestone(simulation_state, arc_id="arc:x", milestone_id="milestone:b", title="B")
    complete_story_arc_milestone(simulation_state, "milestone:a")

    active = list_story_arc_milestones(simulation_state, status="active")
    completed = list_story_arc_milestones(simulation_state, status="completed")

    assert [row["milestone_id"] for row in active] == ["milestone:b"]
    assert [row["milestone_id"] for row in completed] == ["milestone:a"]


def test_story_arc_milestone_state_json_roundtrip():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(simulation_state, arc_id="arc:x", milestone_id="milestone:x", title="X")

    encoded = json.dumps(simulation_state["story_arc_milestone_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_story_arc_milestone_state(decoded)

    assert normalized["arcs"]["arc:x"]["milestones"][0]["milestone_id"] == "milestone:x"


def test_story_arc_milestone_normalize_preserves_canonical_bucket_shape():
    raw = {
        "arcs": {
            "arc:x": {
                "milestones": [
                    {
                        "milestone_id": "milestone:x",
                        "arc_id": "arc:x",
                        "title": "Find the witness",
                        "status": "active",
                    }
                ]
            }
        }
    }

    normalized = normalize_story_arc_milestone_state(raw)

    assert normalized["arcs"]["arc:x"]["milestones"][0]["milestone_id"] == "milestone:x"


def test_story_arc_milestone_normalize_supports_legacy_list_shape():
    raw = {
        "arcs": {
            "arc:x": [
                {
                    "milestone_id": "milestone:x",
                    "arc_id": "arc:x",
                    "title": "Find the witness",
                    "status": "active",
                }
            ]
        }
    }

    normalized = normalize_story_arc_milestone_state(raw)

    assert normalized["arcs"]["arc:x"]["milestones"][0]["milestone_id"] == "milestone:x"


def test_story_arc_milestones_are_bounded_per_arc():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")

    for i in range(40):
        add_story_arc_milestone(
            simulation_state,
            arc_id="arc:x",
            milestone_id=f"milestone:{i}",
            title=f"Milestone {i}",
        )

    assert len(simulation_state["story_arc_milestone_state"]["arcs"]["arc:x"]["milestones"]) <= 30