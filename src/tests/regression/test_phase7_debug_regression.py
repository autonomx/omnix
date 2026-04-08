"""Regression tests for Phase 7 — Creator / GM Debug Tools.

Ensures backward compatibility and deterministic behavior.
"""

from __future__ import annotations

import pytest

from app.rpg.creator.world_debug import (
    explain_faction,
    explain_npc,
    summarize_npc_minds,
    summarize_social_state,
    summarize_tick_changes,
    summarize_world_pressures,
)
from app.rpg.creator.world_gm_tools import (
    force_alliance,
    force_faction_position,
    force_npc_belief,
    inject_event,
    seed_rumor,
    step_ticks,
)
from app.rpg.creator.world_replay import (
    get_snapshot,
    list_snapshots,
    rollback_to_snapshot,
    summarize_timeline,
)


class TestDeterminism:
    """Same input state should produce same debug summaries."""

    def test_summarize_npc_minds_deterministic(self):
        state = {
            "npc_index": {
                "n1": {"name": "Alice", "role": "warrior", "faction_id": "f1", "location_id": "l1"},
                "n2": {"name": "Bob", "role": "mage", "faction_id": "f2", "location_id": "l2"},
            },
            "npc_minds": {
                "n1": {"beliefs": {"player": {"trust": 0.5}}, "goals": [{"goal": "patrol"}], "memory": {"entries": ["e1", "e2"]}},
                "n2": {"beliefs": {"player": {"trust": 0.2}}, "goals": [{"goal": "study"}], "memory": {"entries": []}},
            },
        }

        r1 = summarize_npc_minds(state)
        r2 = summarize_npc_minds(state)
        assert r1 == r2

    def test_summarize_social_state_deterministic(self):
        state = {
            "social_state": {
                "alliances": [{"status": "active", "member_ids": ["f1"]}],
                "group_positions": {"f1": {"stance": "hostile"}},
                "reputation": {"f1": {"player": {"trust": 0.3}}},
            },
            "active_rumors": [{"id": "r1"}],
        }

        r1 = summarize_social_state(state)
        r2 = summarize_social_state(state)
        assert r1 == r2

    def test_summarize_world_pressures_deterministic(self):
        state = {
            "threads": {"t1": {"pressure": 3, "heat": 0, "status": "active"}},
            "factions": {"f1": {"pressure": 2, "heat": 0, "status": "watchful"}},
            "locations": {"l1": {"pressure": 0, "heat": 4, "status": "active"}},
        }

        r1 = summarize_world_pressures(state)
        r2 = summarize_world_pressures(state)
        assert r1 == r2


class TestBackwardCompatibility:
    """Ensure existing patterns still work after Phase 7 additions."""

    def test_inject_event_preserves_existing_events(self):
        state = {
            "tick": 5,
            "events": [{"type": "existing"}],
        }
        result = inject_event(state, {"type": "new"}, reason="gm_injection")
        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "existing"
        assert result["events"][1]["type"] == "new"

    def test_seed_rumor_does_not_overwrite_existing(self):
        state = {
            "social_state": {
                "rumors": [{"id": "old"}],
            },
        }
        result = seed_rumor(state, {"id": "new"})
        rumors = result["social_state"]["rumors"]
        assert len(rumors) == 2
        assert rumors[0]["id"] == "old"
        assert rumors[1]["id"] == "new"

    def test_force_alliance_does_not_modify_other_alliances(self):
        state = {
            "social_state": {
                "alliances": [{"status": "active", "member_ids": ["f1"]}],
            },
        }
        result = force_alliance(state, {"status": "active", "member_ids": ["f2", "f3"]})
        alliances = result["social_state"]["alliances"]
        assert len(alliances) == 2

    def test_rollback_preserves_snapshot_list(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s1", "tick": 1, "state": {"tick": 1}},
                {"snapshot_id": "s2", "tick": 2, "state": {"tick": 2}},
            ],
        }
        result = rollback_to_snapshot(state, "s1")
        assert result["tick"] == 1
        assert result["debug_meta"]["last_step_reason"] == "rollback"


class TestSnapshotOrdering:
    """Snapshot listing remains sorted by tick."""

    def test_unordered_input_sorted_output(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s5", "tick": 5},
                {"snapshot_id": "s1", "tick": 1},
                {"snapshot_id": "s3", "tick": 3},
                {"snapshot_id": "s2", "tick": 2},
                {"snapshot_id": "s4", "tick": 4},
            ]
        }
        result = list_snapshots(state)
        ticks = [s["tick"] for s in result]
        assert ticks == sorted(ticks)

    def test_same_tick_sorted_by_id(self):
        state = {
            "snapshots": [
                {"snapshot_id": "c", "tick": 1},
                {"snapshot_id": "a", "tick": 1},
                {"snapshot_id": "b", "tick": 1},
            ]
        }
        result = list_snapshots(state)
        ids = [s["snapshot_id"] for s in result]
        assert ids == sorted(ids)


class TestRollbackSafety:
    """Rollback does not lose debug_meta structure."""

    def test_rollback_keeps_debug_meta(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s1", "tick": 1, "state": {"tick": 1}},
            ],
            "debug_meta": {"last_step_reason": "manual_step", "last_step_tick": 10},
        }
        result = rollback_to_snapshot(state, "s1")
        assert "debug_meta" in result
        assert result["debug_meta"]["last_step_reason"] == "rollback"
        assert result["debug_meta"]["rollback_snapshot_id"] == "s1"

    def test_rollback_missing_snapshot_unchanged(self):
        state = {"tick": 10, "debug_meta": {"last_step_reason": "auto"}}
        result = rollback_to_snapshot(state, "nonexistent")
        assert result == state


class TestGmOverrideIntegrity:
    """GM overrides persist correctly across operations."""

    def test_multiple_forces_accumulate(self):
        state = {}
        result = force_faction_position(state, "f1", {"stance": "hostile"})
        result = force_faction_position(result, "f2", {"stance": "friendly"})

        overrides = result["gm_overrides"]["forced_faction_positions"]
        assert len(overrides) == 2
        assert "f1" in overrides
        assert "f2" in overrides

    def test_npc_belief_update_accumulates(self):
        state = {}
        result = force_npc_belief(state, "npc1", "player", {"trust": 0.5})
        result = force_npc_belief(result, "npc1", "player", {"trust": 0.8, "fear": 0.3})

        beliefs = result["npc_minds"]["npc1"]["beliefs"]["player"]
        assert beliefs["trust"] == 0.8
        assert beliefs["fear"] == 0.3


class TestTimelineSummary:
    """Timeline summary reflects state accurately."""

    def test_empty_timeline(self):
        state = {}
        result = summarize_timeline(state)
        assert result["tick"] == 0
        assert result["snapshot_count"] == 0
        assert result["event_count"] == 0
        assert result["consequence_count"] == 0

    def test_populated_timeline(self):
        state = {
            "tick": 15,
            "events": list(range(10)),
            "consequences": list(range(5)),
            "snapshots": [
                {"snapshot_id": f"s{i}", "tick": i} for i in range(1, 6)
            ],
        }
        result = summarize_timeline(state)
        assert result["tick"] == 15
        assert result["snapshot_count"] == 5
        assert result["event_count"] == 10
        assert result["consequence_count"] == 5
        assert len(result["recent_snapshots"]) == 5