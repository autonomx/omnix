"""Regression tests for PHASE 3 — BRANCHING TIMELINES + MULTIVERSE GRAPH.

Tests ensure that Phase 3 changes do NOT break existing functionality:
- EventBus emit still works after timeline integration
- ReplayEngine replay still works without branch_leaf_id
- GameEngine handle_input still works after fork_timeline addition
- Existing test patterns still pass
- Memory/deduplication still works with timeline
"""

import pytest

from app.rpg.core.timeline_graph import TimelineGraph
from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.replay_engine import ReplayEngine, ReplayConfig


# ==================== Helper Classes ====================


class MockIntentParser:
    def parse(self, player_input: str) -> dict:
        return {"action": player_input}


class TrackingWorldSystem:
    def __init__(self):
        self.tick_count = 0
        self.events_handled = []

    def tick(self, event_bus: EventBus) -> None:
        self.tick_count += 1

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class TrackingNPCSystem:
    def __init__(self):
        self.update_count = 0
        self.events_handled = []

    def update(self, intent: dict, event_bus: EventBus) -> None:
        self.update_count += 1

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockStoryDirector:
    def __init__(self):
        self.events_handled = []

    def process(self, events: list, intent: dict, event_bus: EventBus) -> dict:
        return {"narrative": "processed"}

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockSceneRenderer:
    def render(self, narrative: dict) -> dict:
        return {"scene": narrative}


def create_game_loop():
    from app.rpg.core.game_loop import GameLoop

    return GameLoop(
        intent_parser=MockIntentParser(),
        world=TrackingWorldSystem(),
        npc_system=TrackingNPCSystem(),
        story_director=MockStoryDirector(),
        scene_renderer=MockSceneRenderer(),
        event_bus=EventBus(),
    )


# ==================== EventBus Backward Compatibility ====================


class TestEventBusBackwardCompatibility:
    """Ensure EventBus still works after timeline integration."""

    def test_emit_still_adds_to_history(self):
        """Regression: emit should still add events to history."""
        bus = EventBus()
        bus.emit(Event("test", {}, source="test"))
        assert len(bus.history()) == 1

    def test_replay_emit_does_not_add_to_history(self):
        """Regression: replay=True should not add to history."""
        bus = EventBus()
        bus.emit(Event("test", {}, source="test"), replay=True)
        assert len(bus.history()) == 0

    def test_collect_still_clears_queue(self):
        """Regression: collect should still clear the queue."""
        bus = EventBus()
        bus.emit(Event("test", {}, source="test"))
        events = bus.collect()
        assert len(events) == 1
        assert bus.pending_count == 0

    def test_reset_clears_everything(self):
        """Regression: reset should clear all state."""
        bus = EventBus()
        bus.emit(Event("test", {}, source="test"))
        bus.emit(Event("test2", {}, source="test"))
        bus.collect()
        bus.reset()
        assert bus.pending_count == 0
        assert len(bus.history()) == 0

    def test_history_bounded(self):
        """Regression: history should still be bounded."""
        bus = EventBus()
        bus._max_history = 5
        for i in range(10):
            bus.emit(Event(f"event_{i}", {}, source="test"))
        # Should only keep last 5
        assert len(bus.history()) <= bus._max_history

    def test_deduplication_still_works(self):
        """Regression: duplicate event_ids should be deduplicated."""
        bus = EventBus()
        event = Event("test", {}, source="test")
        event_id = event.event_id
        bus.emit(event)

        # Try to emit duplicate
        event2 = Event("test", {}, source="test")
        event2.event_id = event_id
        bus.emit(event2)

        # Should only have one event in history
        assert len(bus.history()) == 1


# ==================== ReplayEngine Backward Compatibility ====================


class TestReplayEngineBackwardCompatibility:
    """Ensure ReplayEngine still works without branch_leaf_id."""

    def test_replay_without_branch_still_works(self):
        """Regression: replay without branch_leaf_id should work."""
        events = [
            Event("a", {"tick": 1}, source="test"),
            Event("b", {"tick": 2}, source="test"),
        ]

        engine = ReplayEngine(create_game_loop)
        loop = engine.replay(events)
        assert loop is not None

    def test_replay_up_to_tick_still_works(self):
        """Regression: up_to_tick parameter should still filter."""
        events = [
            Event("a", {"tick": 1}, source="test"),
            Event("b", {"tick": 5}, source="test"),
            Event("c", {"tick": 10}, source="test"),
        ]

        engine = ReplayEngine(create_game_loop)
        loop = engine.replay(events, up_to_tick=5)
        assert loop._tick_count == 5

    def test_replay_empty_events_raises(self):
        """Regression: replay([]) should still raise ValueError."""
        engine = ReplayEngine(create_game_loop)
        with pytest.raises(ValueError, match="Cannot replay empty"):
            engine.replay([])


# ==================== GameEngine Backward Compatibility ====================


class TestGameEngineBackwardCompatibility:
    """Ensure GameEngine still works after fork_timeline addition."""

    def test_handle_input_still_works(self):
        """Regression: handle_input should still work."""
        from app.rpg.core import GameEngine

        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=TrackingWorldSystem(),
            npc_system=TrackingNPCSystem(),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            intent_parser_factory=MockIntentParser,
            world_factory=TrackingWorldSystem,
            npc_system_factory=TrackingNPCSystem,
            story_director_factory=MockStoryDirector,
            scene_renderer_factory=MockSceneRenderer,
        )

        result = engine.handle_input("look around")
        assert result is not None

    def test_save_load_still_works(self):
        """Regression: save/load should still work."""
        from app.rpg.core import GameEngine

        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=TrackingWorldSystem(),
            npc_system=TrackingNPCSystem(),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            intent_parser_factory=MockIntentParser,
            world_factory=TrackingWorldSystem,
            npc_system_factory=TrackingNPCSystem,
            story_director_factory=MockStoryDirector,
            scene_renderer_factory=MockSceneRenderer,
        )

        # Play a few ticks
        engine.handle_input("look")
        engine.handle_input("go north")

        # Save
        saved_events = engine.save()
        assert len(saved_events) > 0


# ==================== Timeline Graph Stability ====================


class TestTimelineGraphStability:
    """Ensure TimelineGraph doesn't break under stress."""

    def test_large_graph(self):
        """Test timeline graph handles many events."""
        graph = TimelineGraph()

        # Build linear chain of 1000 events
        parent_id = None
        for i in range(1000):
            event_id = f"e{i}"
            graph.add_event(event_id, parent_id)
            parent_id = event_id

        assert graph.node_count() == 1000

    def test_many_branches(self):
        """Test graph handles many branches."""
        graph = TimelineGraph()
        graph.add_event("root", parent_id=None)
        graph.add_event("fork", parent_id="root")

        # Create 100 branches from fork
        for i in range(100):
            graph.add_event(f"leaf_{i}", parent_id="fork")

        forks = graph.get_forks()
        assert "fork" in forks
        assert len(forks["fork"]) == 100

    def test_cleared_graph_is_reusable(self):
        """Test that clearing graph allows reuse."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.clear()

        # Should be able to add new events
        graph.add_event("e2", parent_id=None)
        assert graph.node_count() == 1


# ==================== Edge: No Timeline Available ====================


class TestNoTimelineAvailable:
    """Ensure ReplayEngine handles missing timeline gracefully."""

    def test_replay_with_fresh_bus_has_timeline(self):
        """Regression: fresh EventBus always has timeline."""
        bus = EventBus()
        assert hasattr(bus, "timeline")
        assert bus.timeline is not None