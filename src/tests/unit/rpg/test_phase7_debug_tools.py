"""Unit tests for Phase 7 — Creator / GM Debug Tools."""

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

# ===================================================================
# world_debug.py tests
# ===================================================================


class TestSummarizeNpcMinds:
    def test_empty_state(self):
        result = summarize_npc_minds({})
        assert isinstance(result, list)
        assert len(result) == 0

    def test_bounded_output(self):
        npc_minds = {f"npc_{i}": {"beliefs": {}, "goals": [], "memory": {"entries": []}} for i in range(20)}
        state = {"npc_minds": npc_minds, "npc_index": {}}
        result = summarize_npc_minds(state)
        assert len(result) <= 12

    def test_deterministic_ordering(self):
        npc_minds = {
            "npc_b": {"beliefs": {}, "goals": [], "memory": {"entries": []}},
            "npc_a": {"beliefs": {}, "goals": [], "memory": {"entries": []}},
        }
        npc_index = {
            "npc_b": {"name": "Bob", "faction_id": "faction_2"},
            "npc_a": {"name": "Alice", "faction_id": "faction_1"},
        }
        state = {"npc_minds": npc_minds, "npc_index": npc_index}
        result = summarize_npc_minds(state)
        assert len(result) == 2
        assert result[0]["npc_id"] == "npc_a"  # faction_1 before faction_2


class TestSummarizeSocialState:
    def test_empty_state(self):
        result = summarize_social_state({})
        assert isinstance(result, dict)
        assert "active_alliances" in result
        assert "active_rumors" in result
        assert "group_positions" in result
        assert "reputation_sources" in result

    def test_shape_stable(self):
        state = {
            "social_state": {
                "alliances": [{"status": "active", "member_ids": ["f1", "f2"]}],
                "group_positions": {"f1": {"stance": "supportive"}},
                "reputation": {"f1": {"player": {"trust": 0.5}}},
            },
            "active_rumors": [{"id": "r1"}],
        }
        result = summarize_social_state(state)
        assert len(result["active_alliances"]) == 1
        assert len(result["active_rumors"]) == 1
        assert "f1" in result["group_positions"]
        assert result["reputation_sources"] == 1


class TestSummarizeWorldPressures:
    def test_empty_state(self):
        result = summarize_world_pressures({})
        assert "threads" in result
        assert "factions" in result
        assert "locations" in result

    def test_sorted_by_pressure(self):
        state = {
            "threads": {
                "t1": {"pressure": 3, "status": "active"},
                "t2": {"pressure": 5, "status": "critical"},
                "t3": {"pressure": 1, "status": "low"},
            }
        }
        result = summarize_world_pressures(state)
        assert result["threads"][0]["id"] == "t2"  # highest pressure first


class TestExplainNpc:
    def test_missing_npc(self):
        result = explain_npc({}, "nonexistent")
        assert result["npc"]["npc_id"] == "nonexistent"
        assert result["explanation"]["top_goal"] == {}

    def test_npc_with_data(self):
        state = {
            "npc_index": {"npc1": {"name": "Alice", "faction_id": "f1"}},
            "npc_minds": {
                "npc1": {
                    "beliefs": {"player": {"trust": 0.5}},
                    "goals": [{"goal": "explore"}],
                    "memory": {"entries": ["entry1"]},
                    "last_decision": {"reason": "safety"},
                }
            },
        }
        result = explain_npc(state, "npc1")
        assert result["npc"]["name"] == "Alice"
        assert len(result["beliefs"]) == 1
        assert len(result["goals"]) == 1


class TestExplainFaction:
    def test_missing_faction(self):
        result = explain_faction({}, "unknown")
        assert result["faction_id"] == "unknown"
        assert len(result["members"]) == 0

    def test_faction_with_members(self):
        state = {
            "npc_index": {
                "n1": {"name": "Alice", "faction_id": "f1"},
                "n2": {"name": "Bob", "faction_id": "f1"},
            },
            "npc_minds": {
                "n1": {"beliefs": {"player": {}}, "last_decision": {}},
                "n2": {"beliefs": {"player": {}}, "last_decision": {}},
            },
            "social_state": {
                "group_positions": {"f1": {"stance": "hostile"}},
                "alliances": [],
            },
        }
        result = explain_faction(state, "f1")
        assert len(result["members"]) == 2
        assert result["group_position"] == {"stance": "hostile"}


class TestSummarizeTickChanges:
    def test_empty_states(self):
        result = summarize_tick_changes({}, {})
        assert result["tick_before"] == 0
        assert result["tick_after"] == 0
        assert result["new_events"] == []

    def test_new_events(self):
        before = {"tick": 0, "events": [], "consequences": []}
        after = {
            "tick": 1,
            "events": [{"type": "test"}],
            "consequences": [{"type": "c1"}],
        }
        result = summarize_tick_changes(before, after)
        assert result["tick_before"] == 0
        assert result["tick_after"] == 1
        assert len(result["new_events"]) == 1


# ===================================================================
# world_gm_tools.py tests
# ===================================================================


class TestInjectEvent:
    def test_inject_writes_debug_meta(self):
        state = {"tick": 5, "events": []}
        event = {"type": "betrayal", "actor": "player"}
        result = inject_event(state, event, reason="gm_injection")
        assert len(result["events"]) == 1
        assert result["debug_meta"]["last_step_reason"] == "gm_injection"
        assert result["debug_meta"]["last_step_tick"] == 5


class TestSeedRumor:
    def test_seed_rumor(self):
        state = {}
        rumor = {"id": "r1", "text": "secret"}
        result = seed_rumor(state, rumor)
        rumors = result["social_state"]["rumors"]
        assert len(rumors) == 1
        assert rumors[0]["id"] == "r1"


class TestForceAlliance:
    def test_force_alliance(self):
        state = {}
        alliance = {"status": "active", "member_ids": ["f1", "f2"]}
        result = force_alliance(state, alliance)
        alliances = result["social_state"]["alliances"]
        assert len(alliances) == 1


class TestForceFactionPosition:
    def test_force_faction_position(self):
        state = {}
        result = force_faction_position(state, "f1", {"stance": "hostile"})
        assert result["social_state"]["group_positions"]["f1"]["stance"] == "hostile"
        assert result["gm_overrides"]["forced_faction_positions"]["f1"]["stance"] == "hostile"


class TestForceNpcBelief:
    def test_force_npc_belief(self):
        state = {}
        result = force_npc_belief(state, "npc1", "player", {"trust": 0.8, "fear": 0.2})
        belief = result["npc_minds"]["npc1"]["beliefs"]["player"]
        assert belief["trust"] == 0.8
        assert belief["fear"] == 0.2


class TestStepTicks:
    def test_steps_multiple(self):
        calls = []

        def mock_step(payload):
            calls.append(payload)
            payload["metadata"]["simulation_state"]["tick"] += 1
            return payload

        payload = {"metadata": {"simulation_state": {"tick": 0}}}
        result = step_ticks(payload, mock_step, count=3)
        assert len(calls) == 3
        assert result["metadata"]["simulation_state"]["tick"] == 3


# ===================================================================
# world_replay.py tests
# ===================================================================


class TestListSnapshots:
    def test_empty(self):
        assert list_snapshots({}) == []

    def test_sorted_by_tick(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s2", "tick": 2, "label": "b"},
                {"snapshot_id": "s1", "tick": 1, "label": "a"},
            ]
        }
        result = list_snapshots(state)
        assert result[0]["snapshot_id"] == "s1"
        assert result[1]["snapshot_id"] == "s2"

    def test_limited_to_100(self):
        state = {"snapshots": [{"snapshot_id": f"s{i}", "tick": i} for i in range(150)]}
        assert len(list_snapshots(state)) == 100


class TestGetSnapshot:
    def test_found(self):
        state = {"snapshots": [{"snapshot_id": "s1", "tick": 5}]}
        result = get_snapshot(state, "s1")
        assert result["snapshot_id"] == "s1"

    def test_not_found(self):
        assert get_snapshot({}, "missing") == {}


class TestRollbackToSnapshot:
    def test_rollback_sets_debug_meta(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s1", "tick": 5, "state": {"tick": 5, "events": []}}
            ]
        }
        result = rollback_to_snapshot(state, "s1")
        assert result["debug_meta"]["last_step_reason"] == "rollback"
        assert result["debug_meta"]["rollback_snapshot_id"] == "s1"

    def test_missing_returns_current(self):
        state = {"tick": 10}
        result = rollback_to_snapshot(state, "missing")
        assert result == state


class TestSummarizeTimeline:
    def test_empty(self):
        result = summarize_timeline({})
        assert result["tick"] == 0
        assert result["snapshot_count"] == 0
        assert result["event_count"] == 0
        assert result["consequence_count"] == 0

    def test_with_data(self):
        state = {
            "tick": 5,
            "events": [1, 2],
            "consequences": [1],
            "snapshots": [{"snapshot_id": "s1", "tick": 1}],
        }
        result = summarize_timeline(state)
        assert result["tick"] == 5
        assert result["event_count"] == 2
        assert result["consequence_count"] == 1


class TestRegression:
    """Regression tests for deterministic behavior."""

    def test_same_input_same_output(self):
        state = {
            "npc_index": {"n1": {"name": "A", "faction_id": "f1"}},
            "npc_minds": {"n1": {"beliefs": {}, "goals": [], "memory": {"entries": []}}},
            "threads": {"t1": {"pressure": 3}},
            "factions": {},
            "locations": {},
        }

        r1 = summarize_npc_minds(state, limit=5)
        r2 = summarize_npc_minds(state, limit=5)
        assert r1 == r2

    def test_snapshot_listing_sorted(self):
        state = {
            "snapshots": [
                {"snapshot_id": f"s{i}", "tick": i, "hash": "h"}
                for i in [5, 1, 3, 2, 4]
            ]
        }
        result = list_snapshots(state)
        ticks = [s["tick"] for s in result]
        assert ticks == sorted(ticks)

    def test_rollback_preserves_debug_meta(self):
        state = {
            "snapshots": [
                {"snapshot_id": "s1", "tick": 2, "state": {"tick": 2}}
            ],
            "debug_meta": {"last_step_reason": "gm_injection"},
        }
        result = rollback_to_snapshot(state, "s1")
        # rollback overrides but keeps debug_meta structure
        assert "debug_meta" in result
        assert result["debug_meta"]["last_step_reason"] == "rollback"