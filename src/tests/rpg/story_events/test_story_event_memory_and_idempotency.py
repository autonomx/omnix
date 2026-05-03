from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.story_arcs.state import get_story_arc, start_story_arc
from app.rpg.story_events.application import apply_story_event
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_story_event_records_causal_memory():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:bandits_warn_bran",
            "arc_id": "arc:bandit_pressure",
            "kind": "warning",
            "location_id": "tavern_common_room",
            "participants": ["player", "bran"],
            "summary": "The player warned Bran about bandits.",
            "tags": ["bandit", "warning"],
            "actor_id": "player",
            "target_id": "bran",
            "effects": [
                {"type": "memory_event"},
            ],
        },
        turn_index=4,
    )

    rows = retrieve_causal_memories(simulation_state, "bran", tags=["warning"])
    assert result["ok"] is True
    assert rows
    assert rows[0]["event_id"] == "event:bandits_warn_bran"


def test_story_event_idempotency_prevents_double_apply():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", pressure=10)
    event = {
        "event_id": "event:pressure_once",
        "arc_id": "arc:bandit_pressure",
        "effects": [
            {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 20},
        ],
    }

    first = apply_story_event(simulation_state, event, turn_index=1)
    second = apply_story_event(simulation_state, event, turn_index=2)

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    assert first["ok"] is True
    assert second["ok"] is True
    assert second["reason"] == "already_applied"
    assert arc["pressure"] == 30


def test_applied_story_event_state_is_bounded_and_save_safe():
    import json

    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")
    apply_story_event(
        simulation_state,
        {
            "event_id": "event:save_safe",
            "arc_id": "arc:bandit_pressure",
            "summary": "Save safe event.",
            "effects": [],
        },
    )

    encoded = json.dumps(simulation_state["story_event_state"], sort_keys=True)
    decoded = json.loads(encoded)

    assert "event:save_safe" in decoded["applied_events"]