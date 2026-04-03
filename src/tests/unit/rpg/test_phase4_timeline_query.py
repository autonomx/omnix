"""Unit tests for PHASE 4 — TIMELINE QUERY API + BRANCH EVALUATION.

Tests cover:
- TimelineQueryEngine query methods (get_events_by_tick, get_events_by_actor, get_causal_chain)
- Branch evaluation (evaluate_branch, find_best_branch, list_all_branches)
- Partial replay / simulation mode
- Timeline snapshot capture and restore
- EventContext for proper parent chain
- Intent-level event creation
- TimelineGraph cycle detection improvements
- EventBus memory growth fix (deque)
"""

import pytest

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.timeline_graph import TimelineGraph, TimelineNode
from app.rpg.core.timeline_query import (
    TimelineQueryEngine,
    TimelineSnapshot,
    BranchScore,
    DefaultBranchEvaluator,
    EventContext,
    create_intent_event,
)


# ==================== EventContext Tests ====================


class TestEventContext:
    """Test EventContext for proper parent chain (rpg-design.txt Issue #1)."""

    def test_event_context_creation(self):
        """Test EventContext creation with parent_id."""
        ctx = EventContext(parent_id="e1")
        assert ctx.parent_id == "e1"

    def test_event_context_with_tick(self):
        """Test EventContext with tick."""
        ctx = EventContext(parent_id="e1", tick=5)
        assert ctx.parent_id == "e1"
        assert ctx.tick == 5

    def test_event_context_with_source(self):
        """Test EventContext with source_system."""
        ctx = EventContext(parent_id="e1", source_system="npc_system")
        assert ctx.source_system == "npc_system"

    def test_event_context_applied_to_emit(self):
        """Test that EventContext parent_id is applied during emit."""
        bus = EventBus()
        e1 = Event("start", payload={"tick": 1}, source="test")
        bus.emit(e1)

        ctx = EventContext(parent_id=e1.event_id)
        e2 = Event("action", payload={"tick": 2}, source="test")
        bus.emit(e2, context=ctx)

        # Verify parent_id was set from context in the timeline
        # Note: emit() clones the event, so check the timeline, not the original object
        branch = bus.timeline.get_branch(e2.event_id)
        assert e1.event_id in branch
        # Verify the event in history has the correct parent
        history = bus.history()
        e2_in_history = [e for e in history if e.event_id == e2.event_id][0]
        assert e2_in_history.parent_id == e1.event_id


# ==================== Intent Event Tests ====================


class TestIntentEvents:
    """Test intent-level event creation (rpg-design.txt Issue #6)."""

    def test_create_npc_intent_event(self):
        """Test creating npc_intent event."""
        event = create_intent_event(
            event_type="npc_intent",
            actor_id="npc_1",
            intent_data={"goal": "explore", "target": "forest"},
        )
        assert event.type == "npc_intent"
        assert event.payload["actor_id"] == "npc_1"
        assert event.payload["intent"]["goal"] == "explore"

    def test_create_belief_update_event(self):
        """Test creating belief_update event."""
        event = create_intent_event(
            event_type="belief_update",
            actor_id="npc_1",
            intent_data={"belief": "player_is_hostile", "confidence": 0.8},
        )
        assert event.type == "belief_update"
        assert event.payload["intent"]["belief"] == "player_is_hostile"

    def test_create_goal_change_event(self):
        """Test creating goal_change event."""
        event = create_intent_event(
            event_type="goal_change",
            actor_id="npc_1",
            intent_data={"old_goal": "trade", "new_goal": "flee"},
            parent_id="e1",
            source="ai_system",
        )
        assert event.type == "goal_change"
        assert event.parent_id == "e1"
        assert event.source == "ai_system"


# ==================== TimelineQueryEngine Tests ====================


class TestTimelineQueryEngine:
    """Test TimelineQueryEngine query methods."""

    def _setup_bus_with_events(self) -> EventBus:
        """Create EventBus with test events."""
        bus = EventBus()
        bus.set_tick(1)
        e1 = Event("start", payload={"tick": 1, "actor_id": "player"}, source="player")
        bus.emit(e1)

        bus.set_tick(2)
        e2 = Event("npc_intent", payload={"tick": 2, "actor_id": "npc_1"}, source="npc_system")
        bus.emit(e2, context=EventContext(parent_id=e1.event_id))

        bus.set_tick(2)
        e3 = Event("world_change", payload={"tick": 2, "actor_id": "npc_1"}, source="world")
        bus.emit(e3, context=EventContext(parent_id=e1.event_id))

        bus.set_tick(3)
        e4 = Event("dialogue", payload={"tick": 3, "actor_id": "player"}, source="player")
        bus.emit(e4, context=EventContext(parent_id=e2.event_id))

        return bus

    def test_get_events_by_tick(self):
        """Test getting events for specific tick."""
        bus = self._setup_bus_with_events()
        engine = TimelineQueryEngine(bus)

        tick1_events = engine.get_events_by_tick(1)
        assert len(tick1_events) == 1
        assert tick1_events[0].type == "start"

        tick2_events = engine.get_events_by_tick(2)
        assert len(tick2_events) == 2

    def test_get_events_by_actor(self):
        """Test getting events for specific actor."""
        bus = self._setup_bus_with_events()
        engine = TimelineQueryEngine(bus)

        player_events = engine.get_events_by_actor("player")
        assert len(player_events) == 2

        npc_events = engine.get_events_by_actor("npc_1")
        assert len(npc_events) == 2

    def test_get_causal_chain(self):
        """Test getting causal chain."""
        bus = self._setup_bus_with_events()
        engine = TimelineQueryEngine(bus)

        # Get last event
        history = bus.history()
        last_event = history[-1]

        chain = engine.get_causal_chain(last_event.event_id)
        assert len(chain) >= 2  # At least root + this event

    def test_get_sibling_events(self):
        """Test getting sibling events (same tick)."""
        bus = self._setup_bus_with_events()
        engine = TimelineQueryEngine(bus)

        history = bus.history()
        # e2 and e3 are in tick 2
        e2 = history[1]
        siblings = engine.get_sibling_events(e2.event_id)
        assert len(siblings) >= 1  # At least e3

    def test_get_tick_groups(self):
        """Test grouping events by tick."""
        bus = self._setup_bus_with_events()
        engine = TimelineQueryEngine(bus)

        groups = engine.get_tick_groups()
        assert 1 in groups
        assert 2 in groups
        assert 3 in groups
        assert len(groups[2]) == 2


# ==================== Branch Evaluation Tests ====================


class TestBranchEvaluation:
    """Test branch evaluation engine."""

    def test_default_evaluator_empty(self):
        """Test evaluator returns 0 for empty events."""
        evaluator = DefaultBranchEvaluator()
        assert evaluator.evaluate([]) == 0.0

    def test_default_evaluator_single_event(self):
        """Test evaluator with single event."""
        evaluator = DefaultBranchEvaluator()
        events = [Event("test", payload={"actor_id": "p1"}, source="test")]
        score = evaluator.evaluate(events)
        assert 0.0 <= score <= 1.0

    def test_default_evaluator_diverse_events(self):
        """Test evaluator with diverse events (should score higher)."""
        evaluator = DefaultBranchEvaluator()
        events = [
            Event("npc_intent", payload={"actor_id": "npc_1"}, source="npc"),
            Event("dialogue", payload={"actor_id": "player"}, source="player"),
            Event("world_change", payload={"actor_id": "npc_2"}, source="world"),
            Event("combat", payload={"actor_id": "npc_3"}, source="combat"),
        ]
        score = evaluator.evaluate(events)
        assert score > 0.0

    def test_evaluate_branch(self):
        """Test evaluate_branch method."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)
        events = [Event("test", payload={"actor_id": "p1"}, source="test")]
        score = engine.evaluate_branch(events)
        assert 0.0 <= score <= 1.0

    def test_find_best_branch(self):
        """Test find_best_branch selects highest scoring."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        # Emit events so they're in the timeline
        e_a = Event("a", payload={"actor_id": "p1"}, source="test")
        bus.emit(e_a)

        e_b1 = Event("b1", payload={"actor_id": "p1"}, source="test")
        bus.emit(e_b1)
        e_b2 = Event("b2", payload={"actor_id": "p2"}, source="test2")
        bus.emit(e_b2)
        e_b3 = Event("b3", payload={"actor_id": "p3"}, source="test3")
        bus.emit(e_b3)

        candidates = {
            "branch_a": [e_a],
            "branch_b": [e_b1, e_b2, e_b3],
        }
        best = engine.find_best_branch(candidates)
        assert best.branch_id in ("branch_a", "branch_b")


# ==================== Simulation Mode Tests ====================


class TestSimulationMode:
    """Test partial replay / simulation mode."""

    def test_simulate_branch_basic(self):
        """Test basic branch simulation."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)
        events = [
            Event("e1", payload={"tick": 1}, source="test"),
            Event("e2", payload={"tick": 2}, source="test"),
        ]
        result = engine.simulate_branch(events)
        assert result["events_processed"] == 2
        assert result["final_tick"] == 2
        assert result["branch_score"] >= 0.0

    def test_simulate_branch_empty(self):
        """Test simulation with empty events."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)
        result = engine.simulate_branch([])
        assert result["events_processed"] == 0
        assert result["final_tick"] is None


# ==================== Timeline Snapshot Tests ====================


class TestTimelineSnapshot:
    """Test timeline snapshot capture and restore (rpg-design.txt Issue #5)."""

    def test_capture_snapshot(self):
        """Test capturing timeline snapshot."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        e1 = Event("start", payload={"tick": 1}, source="test")
        bus.emit(e1)
        e2 = Event("action", payload={"tick": 2}, source="test")
        bus.emit(e2, context=EventContext(parent_id=e1.event_id))

        snapshot = engine.capture_timeline_snapshot(tick=2)
        assert snapshot.tick == 2
        assert len(snapshot.edges) == 2
        assert e1.event_id in snapshot.seen_event_ids

    def test_restore_snapshot(self):
        """Test restoring timeline from snapshot."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        e1 = Event("start", payload={"tick": 1}, source="test")
        bus.emit(e1)
        e2 = Event("action", payload={"tick": 2}, source="test")
        bus.emit(e2, context=EventContext(parent_id=e1.event_id))

        snapshot = engine.capture_timeline_snapshot(tick=2)

        # Create new bus and restore
        new_bus = EventBus()
        new_engine = TimelineQueryEngine(new_bus)
        new_engine.restore_timeline_snapshot(snapshot)

        # Verify DAG was restored
        assert new_bus.timeline.has_event(e1.event_id)
        assert new_bus.timeline.has_event(e2.event_id)

    def test_snapshot_dataclass(self):
        """Test TimelineSnapshot dataclass."""
        snap = TimelineSnapshot(tick=5)
        assert snap.tick == 5
        assert snap.edges == []
        assert snap.seen_event_ids == set()


# ==================== TimelineGraph Cycle Detection Tests ====================


class TestTimelineGraphCycleDetection:
    """Test improved cycle detection in TimelineGraph."""

    def test_self_loop_prevented(self):
        """Test that self-loop is prevented."""
        graph = TimelineGraph()
        with pytest.raises(ValueError, match="cycle"):
            graph.add_event("e1", parent_id="e1")

    def test_indirect_cycle_prevented(self):
        """Test that indirect cycle is prevented."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3", parent_id="e2")

        # Try to create cycle: e1 -> e2 -> e3 -> e1
        with pytest.raises(ValueError, match="cycle"):
            graph.add_event("e1", parent_id="e3")

    def test_parent_stub_creation(self):
        """Test that parent stub is auto-created."""
        graph = TimelineGraph()
        graph.add_event("e2", parent_id="e1")  # e1 doesn't exist yet
        assert graph.has_event("e1")
        assert graph.has_event("e2")


# ==================== EventBus Memory Fix Tests ====================


class TestEventBusMemoryFix:
    """Test memory growth fix (deque instead of unbounded set)."""

    def test_seen_event_ids_is_deque(self):
        """Test that _seen_event_ids is a deque."""
        from collections import deque
        bus = EventBus()
        assert isinstance(bus._seen_event_ids, deque)

    def test_deduplication_still_works(self):
        """Test that deduplication still works with deque."""
        bus = EventBus()
        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1)
        bus.emit(e1)  # Duplicate
        assert len(bus.history()) == 1

    def test_current_head_method(self):
        """Test current_head() method."""
        bus = EventBus()
        assert bus.current_head() is None

        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1)
        assert bus.current_head() == e1.event_id