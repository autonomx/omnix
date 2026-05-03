from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_event_queue.queue import (
    enqueue_story_event_definition,
    process_story_event_queue,
)
from app.rpg.story_packs.importer import import_story_pack


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "queue_pack",
        "title": "Queue Pack",
        "lore_entries": [{"lore_id": "lore:x", "title": "X"}],
        "story_arcs": [{"arc_id": "arc:x", "title": "X", "stage": "start", "pressure": 10, "linked_lore": ["lore:x"]}],
        "story_events": [
            {
                "event_id": "event:x",
                "arc_id": "arc:x",
                "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}],
            }
        ],
        "escalation_rules": [],
    }


def test_enqueue_story_event_definition_from_registry():
    simulation_state = {}
    import_story_pack(simulation_state, _pack())

    enqueue = enqueue_story_event_definition(
        simulation_state,
        "event:x",
        enqueued_turn=1,
        due_turn=1,
        source="test",
    )
    process = process_story_event_queue(simulation_state, mode="idle", turn_index=1)

    assert enqueue["ok"] is True
    assert process["applied_count"] == 1
    assert get_story_arc(simulation_state, "arc:x")["stage"] == "done"


def test_enqueue_missing_story_event_definition_rejected():
    result = enqueue_story_event_definition({}, "event:missing")

    assert result["ok"] is False
    assert result["reason"] == "story_event_definition_missing"