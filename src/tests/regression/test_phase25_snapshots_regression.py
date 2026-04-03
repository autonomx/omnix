"""PHASE 2.5 — REGRESSION TESTS: Snapshot & Replay

Ensures that Phase 2.5 changes don't break existing functionality:
- EventBus still works with events that don't have event_id/timestamp
- ReplayEngine still works without SnapshotManager
- GameLoop still works without custom SnapshotManager
- Existing event history tracking still works

Run with: python -m pytest src/tests/regression/test_phase25_snapshots_regression.py -v
"""

import unittest
from unittest.mock import MagicMock

from src.app.rpg.core.event_bus import Event, EventBus
from src.app.rpg.core.replay_engine import ReplayEngine, ReplayConfig
from src.app.rpg.core.game_loop import GameLoop
from src.app.rpg.core.snapshot_manager import SnapshotManager


class TestEventBusBackwardsCompatibility(unittest.TestCase):
    """Ensure EventBus still works with existing patterns."""

    def test_emit_event_without_explicit_id(self):
        """Events without explicit event_id should auto-generate one."""
        bus = EventBus()
        event = Event("test", {"data": "value"})
        bus.emit(event)

        history = bus.history()
        self.assertEqual(len(history), 1)
        self.assertIsNotNone(history[0].event_id)

    def test_emit_event_without_explicit_timestamp(self):
        """Events without explicit timestamp should auto-generate one."""
        bus = EventBus()
        event = Event("test", {"data": "value"})
        bus.emit(event)

        history = bus.history()
        self.assertEqual(len(history), 1)
        self.assertIsNotNone(history[0].timestamp)

    def test_old_event_still_works(self):
        """Events created without new fields should still work."""
        # This simulates old code that doesn't use new fields
        event = Event(type="old_style", payload={"key": "value"})
        self.assertEqual(event.type, "old_style")
        self.assertEqual(event.payload["key"], "value")
        # New fields should be auto-populated
        self.assertIsNotNone(event.event_id)
        self.assertIsNotNone(event.timestamp)

    def test_collect_and_peek_unchanged(self):
        """collect() and peek() should work as before."""
        bus = EventBus()
        bus.emit(Event("e1", {"tick": 1}))
        bus.emit(Event("e2", {"tick": 2}))

        peeked = bus.peek()
        self.assertEqual(len(peeked), 2)

        collected = bus.collect()
        self.assertEqual(len(collected), 2)

        # After collect, queue should be empty
        self.assertEqual(len(bus.peek()), 0)

    def test_clear_still_works(self):
        """clear() should remove pending events."""
        bus = EventBus()
        bus.emit(Event("e1", {}))
        bus.emit(Event("e2", {}))
        bus.clear()
        self.assertEqual(len(bus.peek()), 0)

    def test_pending_count_still_works(self):
        """pending_count should return correct value."""
        bus = EventBus()
        bus.emit(Event("e1", {}))
        bus.emit(Event("e2", {}))
        self.assertEqual(bus.pending_count, 2)
        bus.collect()
        self.assertEqual(bus.pending_count, 0)


class TestReplayEngineBackwardsCompatibility(unittest.TestCase):
    """Ensure ReplayEngine still works without SnapshotManager."""

    def test_replay_without_snapshot_manager(self):
        """ReplayEngine should work when loop has no snapshot_manager."""
        events = [
            Event("e1", {"tick": 1}, event_id="e1", timestamp=1.0),
            Event("e2", {"tick": 2}, event_id="e2", timestamp=2.0),
            Event("e3", {"tick": 3}, event_id="e3", timestamp=3.0),
        ]

        def fresh_loop_factory():
            loop = MagicMock()
            loop.world = MagicMock()
            loop.world.serialize.return_value = {}
            loop.world.deserialize = MagicMock()
            loop.npc_system = MagicMock()
            loop.npc_system.serialize.return_value = {}
            loop.npc_system.deserialize = MagicMock()
            # No snapshot_manager attribute
            loop.event_bus = EventBus()
            loop._tick_count = 0
            return loop

        engine = ReplayEngine(fresh_loop_factory)
        loop = engine.replay(events)
        self.assertIsNotNone(loop)

    def test_replay_up_to_tick_without_snapshots(self):
        """Replay up_to_tick without snapshots should replay all events up to tick."""
        events = [
            Event("e1", {"tick": 1}, event_id="e1", timestamp=1.0),
            Event("e2", {"tick": 5}, event_id="e2", timestamp=5.0),
            Event("e3", {"tick": 10}, event_id="e3", timestamp=10.0),
        ]

        received_events = []

        def fresh_loop_factory():
            loop = MagicMock()
            loop.world = MagicMock()
            loop.world.serialize.return_value = {}
            loop.world.deserialize = MagicMock()
            loop.npc_system = MagicMock()
            loop.npc_system.serialize.return_value = {}
            loop.npc_system.deserialize = MagicMock()
            loop.event_bus = EventBus()
            loop._tick_count = 0
            return loop

        engine = ReplayEngine(fresh_loop_factory)
        loop = engine.replay(events, up_to_tick=5)
        self.assertIsNotNone(loop)
        self.assertGreaterEqual(loop._tick_count, 5)

    def test_empty_events_raises_error(self):
        """ReplayEngine should raise ValueError for empty events."""
        engine = ReplayEngine(lambda: MagicMock())
        with self.assertRaises(ValueError):
            engine.replay([])

    def test_get_tick_range_still_works(self):
        """get_tick_range() should return correct min/max ticks."""
        events = [
            Event("e1", {"tick": 10}, event_id="e1"),
            Event("e2", {"tick": 50}, event_id="e2"),
            Event("e3", {"tick": 30}, event_id="e3"),
        ]

        engine = ReplayEngine(lambda: MagicMock())
        min_tick, max_tick = engine.get_tick_range(events)
        self.assertEqual(min_tick, 10)
        self.assertEqual(max_tick, 50)

    def test_get_tick_range_no_ticks(self):
        """get_tick_range() with no tick values should return (None, None)."""
        events = [
            Event("e1", {}, event_id="e1"),
            Event("e2", {}, event_id="e2"),
        ]

        engine = ReplayEngine(lambda: MagicMock())
        min_tick, max_tick = engine.get_tick_range(events)
        self.assertEqual(min_tick, None)
        self.assertEqual(max_tick, None)


class TestGameLoopBackwardsCompatibility(unittest.TestCase):
    """Ensure GameLoop still works without explicit SnapshotManager."""

    def test_gameloop_without_explicit_snapshot_manager(self):
        """GameLoop should create default SnapshotManager when not provided."""
        loop = self._make_simple_loop()
        self.assertIsInstance(loop.snapshot_manager, SnapshotManager)
        self.assertEqual(loop.snapshot_manager._snapshot_interval, 50)

    def test_gameloop_tick_still_works(self):
        """GameLoop.tick() should work normally with default snapshot manager."""
        mock_bus = EventBus()
        mock_world = MagicMock()
        mock_world.serialize.return_value = {}
        mock_world.deserialize = MagicMock()
        mock_npc_system = MagicMock()
        mock_npc_system.serialize.return_value = {}
        mock_npc_system.deserialize = MagicMock()
        mock_story_director = MagicMock()
        mock_story_director.process.return_value = {}
        mock_scene_renderer = MagicMock()
        mock_scene_renderer.render.return_value = {"scene": "ok"}

        loop = GameLoop(
            intent_parser=MagicMock(),
            world=mock_world,
            npc_system=mock_npc_system,
            event_bus=mock_bus,
            story_director=mock_story_director,
            scene_renderer=mock_scene_renderer,
        )

        scene = loop.tick("test input")
        self.assertEqual(scene, {"scene": "ok"})
        self.assertEqual(loop.tick_count, 1)

    def test_gameloop_replay_to_tick_still_works(self):
        """GameLoop.replay_to_tick() should still work with factory."""
        mock_bus = EventBus()
        mock_world = MagicMock()
        mock_world.serialize.return_value = {}
        mock_world.deserialize = MagicMock()
        mock_npc_system = MagicMock()
        mock_npc_system.serialize.return_value = {}
        mock_npc_system.deserialize = MagicMock()
        mock_story_director = MagicMock()
        mock_story_director.process.return_value = {}
        mock_scene_renderer = MagicMock()
        mock_scene_renderer.render.return_value = {"scene": "ok"}

        loop = GameLoop(
            intent_parser=MagicMock(),
            world=mock_world,
            npc_system=mock_npc_system,
            event_bus=mock_bus,
            story_director=mock_story_director,
            scene_renderer=mock_scene_renderer,
        )

        events = [Event("e1", {"tick": 1}, event_id="e1", timestamp=1.0)]

        def factory():
            return GameLoop(
                intent_parser=MagicMock(),
                world=MagicMock(),
                npc_system=MagicMock(),
                event_bus=EventBus(),
                story_director=MagicMock(),
                scene_renderer=MagicMock(),
            )

        replayed = loop.replay_to_tick(events, 1, loop_factory=factory)
        self.assertIsNotNone(replayed)

    def _make_simple_loop(self):
        """Helper to create a minimal GameLoop."""
        return GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=EventBus(),
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )


if __name__ == "__main__":
    unittest.main()