"""Phase 30 — World Events & Consequences Unit Tests."""

import pytest
from app.rpg.creator.world_events import (
    _faction_event,
    _location_event,
    _thread_event,
    generate_consequences,
    generate_world_events,
)
from app.rpg.creator.world_simulation import (
    build_initial_simulation_state,
    step_simulation_state,
)


def _minimal_setup() -> dict:
    return {
        "setup_id": "test_setup",
        "metadata": {"regenerated_threads": []},
        "factions": [],
        "locations": [],
        "npc_seeds": [],
    }


# ---------------------------------------------------------------------------
# Build initial state shape tests
# ---------------------------------------------------------------------------


def test_build_initial_simulation_state_shape():
    state = build_initial_simulation_state(_minimal_setup())
    assert "tick" in state
    assert "threads" in state
    assert "factions" in state
    assert "locations" in state
    assert "history" in state
    assert "events" in state
    assert "consequences" in state
    assert "step_hash" in state


def test_step_simulation_state_returns_expected_shape():
    result = step_simulation_state(_minimal_setup())
    assert "next_setup" in result
    assert "before_state" in result
    assert "after_state" in result
    assert "events" in result
    assert "consequences" in result
    # Summary is stored in history, not as a top-level key
    assert "history" in result["after_state"]


def test_step_simulation_state_generates_events_and_consequences():
    result = step_simulation_state(_minimal_setup())
    assert isinstance(result["events"], list)
    assert isinstance(result["consequences"], list)


def test_step_hash_is_deterministic_for_same_input():
    a = step_simulation_state(_minimal_setup())
    b = step_simulation_state(_minimal_setup())
    assert a["after_state"]["step_hash"] == b["after_state"]["step_hash"]


# ---------------------------------------------------------------------------
# Event generation unit tests
# ---------------------------------------------------------------------------


def test_thread_event_escalation():
    before = {"pressure": 1, "status": "low"}
    after = {"pressure": 2, "status": "active"}
    evt = _thread_event("t1", before, after)
    assert evt is not None
    assert evt["type"] == "thread_escalation"
    assert evt["entity_id"] == "t1"
    assert evt["severity"] == "active"


def test_thread_event_cooling():
    before = {"pressure": 3, "status": "active"}
    after = {"pressure": 1, "status": "low"}
    evt = _thread_event("t2", before, after)
    assert evt is not None
    assert evt["type"] == "thread_cooling"
    assert evt["entity_id"] == "t2"
    assert evt["severity"] == "low"


def test_thread_event_no_change():
    before = {"pressure": 2, "status": "active"}
    after = {"pressure": 2, "status": "active"}
    evt = _thread_event("t3", before, after)
    assert evt is None


def test_faction_event_status_change():
    before = {"status": "stable"}
    after = {"status": "watchful"}
    evt = _faction_event("f1", before, after)
    assert evt is not None
    assert evt["type"] == "faction_reaction"
    assert evt["entity_id"] == "f1"


def test_faction_event_no_change():
    before = {"status": "stable"}
    after = {"status": "stable"}
    evt = _faction_event("f1", before, after)
    assert evt is None


def test_location_event_hotspot():
    before = {"heat": 2, "status": "active"}
    after = {"heat": 4, "status": "hot"}
    evt = _location_event("l1", before, after)
    assert evt is not None
    assert evt["type"] == "location_hotspot"
    assert evt["entity_id"] == "l1"


def test_location_event_cooling():
    before = {"heat": 4, "status": "hot"}
    after = {"heat": 2, "status": "active"}
    evt = _location_event("l2", before, after)
    assert evt is not None
    assert evt["type"] == "location_cooling"


def test_location_event_no_change():
    before = {"heat": 2, "status": "active"}
    after = {"heat": 2, "status": "active"}
    evt = _location_event("l3", before, after)
    assert evt is None


# ---------------------------------------------------------------------------
# generate_world_events integration test
# ---------------------------------------------------------------------------


def test_generate_world_events_from_diff():
    diff = {
        "threads_changed": [
            {
                "id": "t1",
                "before": {"pressure": 1, "status": "low"},
                "after": {"pressure": 3, "status": "active"},
            }
        ],
        "factions_changed": [
            {"id": "f1", "before": {"status": "stable"}, "after": {"status": "watchful"}}
        ],
        "locations_changed": [
            {"id": "l1", "before": {"heat": 1, "status": "quiet"}, "after": {"heat": 4, "status": "hot"}}
        ],
    }
    events = generate_world_events(diff)
    assert len(events) == 3
    types = {e["type"] for e in events}
    assert "thread_escalation" in types
    assert "faction_reaction" in types
    assert "location_hotspot" in types


def test_generate_world_events_empty_diff():
    diff = {"threads_changed": [], "factions_changed": [], "locations_changed": []}
    events = generate_world_events(diff)
    assert events == []


def test_generate_world_events_missing_keys():
    diff = {}
    events = generate_world_events(diff)
    assert events == []


# ---------------------------------------------------------------------------
# consequence generation tests
# ---------------------------------------------------------------------------


def test_generate_consequences_from_events():
    events = [
        {"type": "thread_escalation", "entity_id": "t1", "event_id": "evt1"},
        {"type": "faction_reaction", "entity_id": "f1", "event_id": "evt2"},
        {"type": "location_hotspot", "entity_id": "l1", "event_id": "evt3"},
    ]
    consequences = generate_consequences(events)
    assert len(consequences) == 3
    assert consequences[0]["type"] == "pressure_increase"
    assert consequences[1]["type"] == "faction_response"
    assert consequences[2]["type"] == "hotspot"


def test_generate_consequences_ignores_unknown_types():
    events = [
        {"type": "unknown_event", "entity_id": "x1", "event_id": "evt1"}
    ]
    consequences = generate_consequences(events)
    assert consequences == []


def test_generate_consequences_safe_handles_none():
    consequences = generate_consequences(None)
    assert consequences == []


# ---------------------------------------------------------------------------
# advance_world_simulation service test
# ---------------------------------------------------------------------------


def test_advance_world_simulation_service():
    from app.rpg.services.adventure_builder_service import advance_world_simulation

    result = advance_world_simulation(_minimal_setup())
    assert result["success"] is True
    assert "updated_setup" in result
    assert "simulation_state" in result
    assert "simulation_diff" in result
    assert "summary" in result
    assert "events" in result
    assert "consequences" in result