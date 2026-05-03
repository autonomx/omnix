import json

from app.rpg.story_event_queue.queue import enqueue_story_event
from app.rpg.story_event_queue.state import normalize_story_event_queue_state


def test_story_event_queue_state_json_roundtrip():
    simulation_state = {}
    enqueue_story_event(
        simulation_state,
        {"event_id": "event:x", "effects": []},
        enqueued_turn=1,
        due_turn=3,
    )

    encoded = json.dumps(simulation_state["story_event_queue_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_story_event_queue_state(decoded)

    assert normalized["pending"][0]["event_id"] == "event:x"
    assert normalized["pending"][0]["due_turn"] == 3


def test_story_event_queue_pending_is_bounded():
    simulation_state = {}
    for i in range(250):
        enqueue_story_event(
            simulation_state,
            {"event_id": f"event:{i}", "effects": []},
            enqueued_turn=1,
            due_turn=i,
        )

    assert len(simulation_state["story_event_queue_state"]["pending"]) <= 200