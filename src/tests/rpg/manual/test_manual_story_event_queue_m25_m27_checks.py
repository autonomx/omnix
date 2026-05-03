from app.rpg.story_arcs.state import start_story_arc
from tests.rpg.manual.story_event_queue_m25_m27_checks import (
    run_story_event_queue_m25_m27_checks,
)


def test_manual_story_event_queue_enqueue_and_process_checks():
    session = {"simulation_state": {}}
    start_story_arc(session["simulation_state"], "arc:x", stage="start")

    enqueue = run_story_event_queue_m25_m27_checks(
        checks=[
            {
                "type": "story_event_queue_enqueue",
                "event": {
                    "event_id": "event:x",
                    "arc_id": "arc:x",
                    "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
                },
                "due_turn": 1,
                "expected_ok": True,
                "expected_queued": True,
            }
        ],
        result={},
        session=session,
    )[0]
    process = run_story_event_queue_m25_m27_checks(
        checks=[
            {
                "type": "story_event_queue_process",
                "mode": "idle",
                "turn_index": 1,
                "expected_applied_count": 1,
            }
        ],
        result={},
        session=session,
    )[0]

    assert enqueue["ok"] is True
    assert process["ok"] is True


def test_manual_story_event_queue_pending_check():
    session = {"simulation_state": {}}
    start_story_arc(session["simulation_state"], "arc:x", stage="start")
    run_story_event_queue_m25_m27_checks(
        checks=[
            {
                "type": "story_event_queue_enqueue",
                "event": {"event_id": "event:x", "effects": []},
                "due_turn": 5,
                "expected_ok": True,
            }
        ],
        result={},
        session=session,
    )
    pending = run_story_event_queue_m25_m27_checks(
        checks=[
            {
                "type": "story_event_queue_pending",
                "expected_count": 1,
                "expected_event_id": "event:x",
            }
        ],
        result={},
        session=session,
    )[0]

    assert pending["ok"] is True