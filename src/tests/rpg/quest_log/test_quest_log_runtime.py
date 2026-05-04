from app.rpg.quest_log.runtime import (
    build_objective_tracker_payload,
    build_quest_log_payload,
    pin_objective,
    unpin_objective,
)
from app.rpg.story_arcs.milestones import (
    add_story_arc_milestone,
    complete_story_arc_milestone,
)
from app.rpg.story_arcs.state import start_story_arc


def _state_with_objectives():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:a",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
        quest_id="quest:witness",
        priority=80,
    )
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:b",
        title="Inspect the road",
        objective_text="Inspect the road outside town.",
        quest_id="quest:witness",
        priority=50,
    )
    return simulation_state


def test_quest_log_payload_projects_active_objectives():
    simulation_state = _state_with_objectives()

    payload = build_quest_log_payload(simulation_state)

    assert payload["ok"] is True
    assert payload["format_version"] == "quest_log_v1"
    assert [row["objective_id"] for row in payload["active_objectives"]] == [
        "milestone:a",
        "milestone:b",
    ]
    assert payload["quest_groups"][0]["quest_id"] == "quest:witness"


def test_objective_tracker_is_bounded():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    for i in range(20):
        add_story_arc_milestone(
            simulation_state,
            arc_id="arc:x",
            milestone_id=f"milestone:{i}",
            title=f"Objective {i}",
            priority=i,
        )

    tracker = build_objective_tracker_payload(simulation_state, limit=8)

    assert tracker["ok"] is True
    assert len(tracker["objectives"]) <= 8


def test_pin_objective_moves_it_to_tracker_top():
    simulation_state = _state_with_objectives()

    result = pin_objective(simulation_state, "milestone:b", turn_index=2)
    tracker = build_objective_tracker_payload(simulation_state, limit=8)

    assert result["ok"] is True
    assert result["reason"] == "pinned"
    assert tracker["objectives"][0]["objective_id"] == "milestone:b"
    assert tracker["objectives"][0]["pinned"] is True


def test_unpin_objective_removes_pin():
    simulation_state = _state_with_objectives()
    pin_objective(simulation_state, "milestone:b", turn_index=2)

    result = unpin_objective(simulation_state, "milestone:b", turn_index=3)
    tracker = build_objective_tracker_payload(simulation_state, limit=8)

    assert result["ok"] is True
    assert result["reason"] == "unpinned"
    assert all(row["pinned"] is False for row in tracker["objectives"])


def test_pin_missing_or_completed_objective_rejected():
    simulation_state = _state_with_objectives()
    complete_story_arc_milestone(simulation_state, "milestone:a", turn_index=4)

    completed = pin_objective(simulation_state, "milestone:a")
    missing = pin_objective(simulation_state, "milestone:missing")

    assert completed["ok"] is False
    assert completed["reason"] == "objective_not_active"
    assert missing["ok"] is False
    assert missing["reason"] == "objective_not_active"


def test_completed_objectives_appear_in_quest_log_completed_section():
    simulation_state = _state_with_objectives()
    complete_story_arc_milestone(simulation_state, "milestone:a", turn_index=4)

    payload = build_quest_log_payload(simulation_state)

    assert [row["objective_id"] for row in payload["active_objectives"]] == ["milestone:b"]
    assert [row["objective_id"] for row in payload["completed_objectives"]] == ["milestone:a"]