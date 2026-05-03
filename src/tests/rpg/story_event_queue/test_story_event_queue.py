from app.rpg.story_arcs.state import get_story_arc, start_story_arc
from app.rpg.story_event_queue.queue import enqueue_story_event, process_story_event_queue
from app.rpg.story_events.state import get_applied_story_event


def test_enqueue_story_event_does_not_apply_immediately():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", stage="start")
    result = enqueue_story_event(
        simulation_state,
        {
            "event_id": "event:x",
            "arc_id": "arc:x",
            "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
        },
        enqueued_turn=1,
        delay_turns=2,
    )

    assert result["ok"] is True
    assert result["queued"] is True
    assert get_story_arc(simulation_state, "arc:x")["stage"] == "start"
    assert get_applied_story_event(simulation_state, "event:x") is None


def test_process_story_event_queue_waits_until_due_turn():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", stage="start")
    enqueue_story_event(
        simulation_state,
        {
            "event_id": "event:x",
            "arc_id": "arc:x",
            "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
        },
        enqueued_turn=1,
        delay_turns=2,
    )

    early = process_story_event_queue(simulation_state, mode="idle", turn_index=2)
    due = process_story_event_queue(simulation_state, mode="idle", turn_index=3)

    assert early["applied_count"] == 0
    assert due["applied_count"] == 1
    assert get_story_arc(simulation_state, "arc:x")["stage"] == "done"


def test_story_event_queue_does_not_process_in_unsafe_mode():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", stage="start")
    enqueue_story_event(
        simulation_state,
        {
            "event_id": "event:x",
            "arc_id": "arc:x",
            "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
        },
        enqueued_turn=1,
        due_turn=1,
    )

    result = process_story_event_queue(simulation_state, mode="combat", turn_index=5)

    assert result["reason"] == "unsafe_mode"
    assert result["applied_count"] == 0
    assert get_story_arc(simulation_state, "arc:x")["stage"] == "start"


def test_story_event_queue_prevents_duplicate_event_application():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", stage="start")
    event = {
        "event_id": "event:x",
        "arc_id": "arc:x",
        "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
    }
    first_enqueue = enqueue_story_event(simulation_state, event, enqueued_turn=1, due_turn=1)
    second_enqueue = enqueue_story_event(simulation_state, event, enqueued_turn=1, due_turn=1)
    first_process = process_story_event_queue(simulation_state, mode="idle", turn_index=1)
    second_process = process_story_event_queue(simulation_state, mode="idle", turn_index=2)

    assert first_enqueue["queued"] is True
    assert second_enqueue["queued"] is False
    assert first_process["applied_count"] == 1
    assert second_process["applied_count"] == 0


def test_story_event_queue_records_failed_event_history():
    simulation_state = {}
    enqueue_story_event(
        simulation_state,
        {
            "event_id": "event:bad",
            "arc_id": "arc:missing",
            "effects": [{"type": "arc_stage_set", "arc_id": "arc:missing", "stage": "done"}],
        },
        enqueued_turn=1,
        due_turn=1,
    )

    result = process_story_event_queue(simulation_state, mode="idle", turn_index=1)
    history = simulation_state["story_event_queue_state"]["history"]

    assert result["applied_count"] == 0
    assert history[0]["status"] == "failed"
    assert history[0]["event_id"] == "event:bad"