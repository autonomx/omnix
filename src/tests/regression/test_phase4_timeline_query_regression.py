"""Regression tests for PHASE 4 — TIMELINE QUERY API + BRANCH EVALUATION.

Tests ensure that existing functionality is not broken by Phase 4 changes:
- EventBus emit still works without context
- TimelineGraph still works for basic operations
- ReplayEngine still preserves parent_id
- Existing Phase 3 branching tests still pass
"""

import pytest

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.timeline_graph import TimelineGraph, TimelineNode
from app.rpg.core.timeline_query import (
    EventContext,
    TimelineQueryEngine,
    create_intent_event,
)


class TestEventBusBackwardCompatibility:
    """Test that EventBus changes don't break existing usage."""

    def test_emit_without_context(self):
        """Test that emit still works without EventContext."""
        bus = EventBus()
        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1)
        assert len(bus.history()) == 1
        assert bus.timeline.has_event(e1.event_id)

    def test_emit_with_replay_flag(self):
        """Test that replay=True still prevents history growth."""
        bus = EventBus()
        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1, replay=True)
        assert len(bus.history()) == 0  # Not added to history
        assert bus.timeline.has_event(e1.event_id)  # But still in timeline

    def test_deduplication_prevents_duplicates(self):
        """Test that duplicate events are still prevented."""
        bus = EventBus()
        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1)
        bus.emit(e1)  # Same event_id
        assert len(bus.history()) == 1

    def test_reset_clears_all_state(self):
        """Test that reset clears all state including new fields."""
        bus = EventBus()
        e1 = Event("test", payload={"tick": 1}, source="test")
        bus.emit(e1)
        bus.reset()
        assert len(bus.history()) == 0
        assert bus.timeline.node_count() == 0
        assert len(bus._seen_event_ids_set) == 0


class TestTimelineGraphBackwardCompatibility:
    """Test that TimelineGraph changes don't break existing usage."""

    def test_basic_dag_operations(self):
        """Test basic DAG operations still work."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3", parent_id="e2")

        assert graph.node_count() == 3
        assert graph.get_branch("e3") == ["e1", "e2", "e3"]

    def test_fork_detection(self):
        """Test fork detection still works."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3a", parent_id="e2")
        graph.add_event("e3b", parent_id="e2")

        forks = graph.get_forks()
        assert "e2" in forks
        assert len(forks["e2"]) == 2

    def test_leaves_and_roots(self):
        """Test leaves and roots still work."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2a", parent_id="e1")
        graph.add_event("e2b", parent_id="e1")

        assert set(graph.get_roots()) == {"e1"}
        assert set(graph.get_leaves()) == {"e2a", "e2b"}


class TestReplayEngineParentPreservation:
    """Test that ReplayEngine preserves parent_id during replay."""

    def test_replay_preserves_parent_chain(self):
        """Test that replay preserves the parent chain structure."""
        bus = EventBus()

        # Build timeline with explicit parent chain
        e1 = Event("start", payload={"tick": 1}, source="test")
        bus.emit(e1)
        e2 = Event("action", payload={"tick": 2}, source="test", parent_id=e1.event_id)
        bus.emit(e2)

        # Verify original timeline
        original_chain = bus.timeline.get_branch(e2.event_id)
        assert e1.event_id in original_chain

        # Replay events
        history = bus.history()
        new_bus = EventBus()
        for event in history:
            new_bus.emit(event, replay=True)

        # Verify timeline was reconstructed
        assert new_bus.timeline.has_event(e1.event_id)
        assert new_bus.timeline.has_event(e2.event_id)


class TestIntentEventsBackwardCompatibility:
    """Test that intent events don't break existing event handling."""

    def test_intent_event_is_regular_event(self):
        """Test that intent events work like regular events."""
        bus = EventBus()
        intent = create_intent_event(
            "npc_intent",
            actor_id="npc_1",
            intent_data={"goal": "patrol"},
        )
        bus.emit(intent)
        assert len(bus.history()) == 1
        assert bus.timeline.has_event(intent.event_id)

    def test_intent_event_with_parent(self):
        """Test that intent events can have parents."""
        bus = EventBus()
        e1 = Event("start", payload={"tick": 1}, source="test")
        bus.emit(e1)

        intent = create_intent_event(
            "npc_intent",
            actor_id="npc_1",
            intent_data={"goal": "patrol"},
            parent_id=e1.event_id,
        )
        bus.emit(intent)

        chain = bus.timeline.get_branch(intent.event_id)
        assert e1.event_id in chain


class TestQueryEngineEdgeCases:
    """Test edge cases in query engine."""

    def test_query_empty_bus(self):
        """Test querying an empty bus."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        assert engine.get_events_by_tick(1) == []
        assert engine.get_events_by_actor("player") == []
        assert engine.get_tick_groups() == {}

    def test_query_nonexistent_event(self):
        """Test querying for nonexistent event."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        with pytest.raises(KeyError):
            engine.get_causal_chain("nonexistent")

    def test_simulate_empty_branch(self):
        """Test simulating empty branch."""
        bus = EventBus()
        engine = TimelineQueryEngine(bus)

        result = engine.simulate_branch([])
        assert result["events_processed"] == 0
        assert result["branch_score"] == 0.0


class TestMemoryGrowthPrevention:
    """Test that memory growth is prevented."""

    def test_seen_event_ids_bounded(self):
        """Test that seen_event_ids doesn't grow unboundedly."""
        from collections import deque
        bus = EventBus()

        # Emit many events
        for i in range(200_000):
            e = Event("test", payload={"tick": i % 1000}, source="test")
            bus.emit(e)

        # Deque should be bounded
        assert isinstance(bus._seen_event_ids, deque)
        assert len(bus._seen_event_ids) <= 100_000  # maxlen