"""Phase 30 — World Events & Consequences Functional Tests."""

import pytest

from app.rpg.creator.world_events import generate_consequences, generate_world_events
from app.rpg.creator.world_simulation import (
    build_initial_simulation_state,
    compute_simulation_diff,
    step_simulation_state,
    summarize_simulation_step,
)


def _adventure_setup_with_content():
    """Build a minimal setup with threads, factions, and locations."""
    return {
        "setup_id": "func_test_1",
        "metadata": {
            "regenerated_threads": [
                {
                    "thread_id": "thr_1",
                    "faction_ids": ["fac_a", "fac_b"],
                    "location_ids": ["loc_1"],
                }
            ],
        },
        "factions": [
            {"faction_id": "fac_a", "name": "Faction A"},
            {"faction_id": "fac_b", "name": "Faction B"},
        ],
        "locations": [
            {"location_id": "loc_1", "name": "Location One"},
        ],
        "npc_seeds": [
            {"npc_id": "npc_1", "location_id": "loc_1"},
        ],
    }


def _setup_with_multiple_threads():
    """Setup with multiple threads to trigger multiple event types."""
    return {
        "setup_id": "func_test_2",
        "metadata": {
            "regenerated_threads": [
                {
                    "thread_id": "thr_hot",
                    "faction_ids": ["fac_a"],
                    "location_ids": ["loc_hot"],
                },
                {
                    "thread_id": "thr_calm",
                    "faction_ids": ["fac_a"],
                    "location_ids": ["loc_calm"],
                },
            ],
        },
        "factions": [
            {"faction_id": "fac_a", "name": "Dominant Faction"},
        ],
        "locations": [
            {"location_id": "loc_hot", "name": "Hot Location"},
            {"location_id": "loc_calm", "name": "Calm Location"},
        ],
        "npc_seeds": [
            {"npc_id": "npc_1", "location_id": "loc_hot"},
            {"npc_id": "npc_2", "location_id": "loc_hot"},
            {"npc_id": "npc_3", "location_id": "loc_calm"},
        ],
    }


# ---------------------------------------------------------------------------
# Functional test: initial state has empty events/consequences
# ---------------------------------------------------------------------------


def test_initial_state_has_empty_events():
    setup = _adventure_setup_with_content()
    state = build_initial_simulation_state(setup)
    assert state["events"] == []
    assert state["consequences"] == []


# ---------------------------------------------------------------------------
# Functional test: stepping produces events/consequences in after_state
# ---------------------------------------------------------------------------


def test_step_produces_events_in_after_state():
    setup = _adventure_setup_with_content()
    result = step_simulation_state(setup)
    after = result["after_state"]

    # Ensure the step actually ran
    assert after["tick"] == 1

    # Events and consequences should be lists
    assert isinstance(after["events"], list)
    assert isinstance(after["consequences"], list)


# ---------------------------------------------------------------------------
# Functional test: simulation summary lines include event/consequence counts
# ---------------------------------------------------------------------------


def test_summary_includes_event_counts():
    diff = {
        "threads_changed": [
            {"id": "t1", "before": {"pressure": 1, "status": "low"}, "after": {"pressure": 2, "status": "active"}}
        ],
        "factions_changed": [],
        "locations_changed": [],
    }
    events = [{"type": "thread_escalation", "entity_id": "t1"}]
    consequences = [{"type": "pressure_increase", "entity_id": "t1"}]
    summary = summarize_simulation_step(diff, events=events, consequences=consequences)
    assert "1 world event" in ", ".join(summary)
    assert "1 consequence" in ", ".join(summary)


# ---------------------------------------------------------------------------
# Functional test: multiple steps accumulate history
# ---------------------------------------------------------------------------


def test_multiple_steps_accumulate_history():
    setup = _adventure_setup_with_content()

    # Step 1
    result1 = step_simulation_state(setup)
    updated1 = result1["next_setup"]

    # Step 2
    result2 = step_simulation_state(updated1)
    history = result2["after_state"].get("history", [])
    assert len(history) == 2
    assert history[0]["tick"] == 1
    assert history[1]["tick"] == 2


# ---------------------------------------------------------------------------
# Functional test: event generation from real diff
# ---------------------------------------------------------------------------


def test_events_from_real_diff():
    state_a = {
        "tick": 0,
        "threads": {"t1": {"pressure": 1, "status": "low"}},
        "factions": {"f1": {"pressure": 0, "status": "stable"}},
        "locations": {"l1": {"heat": 0, "status": "quiet"}},
    }
    state_b = {
        "tick": 1,
        "threads": {"t1": {"pressure": 3, "status": "active"}},
        "factions": {"f1": {"pressure": 1, "status": "watchful"}},
        "locations": {"l1": {"heat": 4, "status": "hot"}},
    }

    diff = compute_simulation_diff(state_a, state_b)
    events = generate_world_events(diff)
    consequences = generate_consequences(events)

    assert len(events) >= 1
    assert len(consequences) >= 0