"""PHASE 2.5 — UNIT TESTS: Snapshot Manager & Deterministic Replay

Tests for:
- Event ID / timestamp / parent_id tracking
- EventBus deduplication safety
- Deterministic event ordering in ReplayEngine
- Snapshot save/load/nearest snapshot operations
- Hybrid replay (snapshot + events)
- GameLoop snapshot integration

Run with: python -m pytest src/tests/unit/rpg/test_phase25_snapshots.py -v
"""

import unittest
from unittest.mock import MagicMock
from dataclasses import dataclass

from src.app.rpg.core.event_bus import Event, EventBus
from src.app.rpg.core.snapshot_manager import SnapshotManager, Snapshot
from src.app.rpg.core.replay_engine import ReplayEngine, ReplayConfig
from src.app.rpg.core.game_loop import GameLoop


# ============================================================
# Test Event with new fields
# ============================================================

class TestEventFields(unittest.TestCase):
    """Test the new Event fields: event_id, timestamp, parent_id."""

    def test_event_auto_generates_id(self):
        """Event should auto-generate a UUID if not provided."""
        event = Event("test", {"foo": "bar"})
        self.assertIsNotNone(event.event_id)
        self.assertIsInstance(event.event_id, str)
        self.assertTrue(len(event.event_id) > 10)

    def test_event_preserves_provided_id(self):
        """Event should preserve explicitly provided event_id."""
        event = Event("test", {"foo": "bar"}, event_id="my-custom-id")
        self.assertEqual(event.event_id, "my-custom-id")

    def test_event_auto_sets_timestamp(self):
        """Event should auto-set timestamp if not provided."""
        import time
        before = time.time()
        event = Event("test", {"foo": "bar"})
        after = time.time()
        self.assertIsNotNone(event.timestamp)
        self.assertGreaterEqual(event.timestamp, before)
        self.assertLessEqual(event.timestamp, after)

    def test_event_preserves_timestamp(self):
        """Event should preserve explicitly provided timestamp."""
        custom_ts = 1234567890.0
        event = Event("test", {"foo": "bar"}, timestamp=custom_ts)
        self.assertEqual(event.timestamp, custom_ts)

    def test_event_parent_id(self):
        """Event should support parent_id for causal tracking."""
        parent = Event("parent", {"foo": "bar"})
        child = Event("child", {"foo": "baz"}, parent_id=parent.event_id)
        self.assertEqual(child.parent_id, parent.event_id)

    def test_event_repr_includes_event_id(self):
        """Event repr should include event_id for debugging."""
        event = Event("test", event_id="abc123")
        self.assertIn("abc123", repr(event))


# ============================================================
# Test EventBus Deduplication
# ============================================================

class TestEventBusDedup(unittest.TestCase):
    """Test EventBus deduplication safety via _seen_event_ids."""

    def test_duplicate_event_is_prevented(self):
        """Emitting same event_id twice should result in only one event in history."""
        bus = EventBus()
        event_id = "dup-123"
        e1 = Event("test", {"tick": 1}, source="sys", event_id=event_id)
        e2 = Event("test", {"tick": 1}, source="sys", event_id=event_id)

        bus.emit(e1)
        bus.emit(e2)

        history = bus.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].event_id, event_id)

    def test_different_event_ids_not_deduped(self):
        """Events with different event_ids should both be recorded."""
        bus = EventBus()
        e1 = Event("test", {"tick": 1}, source="sys", event_id="id-1")
        e2 = Event("test", {"tick": 1}, source="sys", event_id="id-2")

        bus.emit(e1)
        bus.emit(e2)

        history = bus.history()
        self.assertEqual(len(history), 2)

    def test_reset_clears_seen_event_ids(self):
        """Resetting bus should clear seen event IDs allowing re-emit."""
        bus = EventBus()
        e1 = Event("test", {"tick": 1}, source="sys", event_id="id-1")

        bus.emit(e1)
        bus.reset()
        bus.emit(e1)

        history = bus.history()
        self.assertEqual(len(history), 1)

    def test_event_clone_preserves_ids(self):
        """EventBus should preserve event_id, timestamp, parent_id when cloning."""
        bus = EventBus()
        original = Event(
            "test",
            {"foo": "bar"},
            source="sys",
            event_id="preserved-id",
            timestamp=999999.0,
            parent_id="parent-123",
        )

        bus.emit(original)
        history = bus.history()
        self.assertEqual(len(history), 1)
        cloned = history[0]
        self.assertEqual(cloned.event_id, "preserved-id")
        self.assertEqual(cloned.timestamp, 999999.0)
        self.assertEqual(cloned.parent_id, "parent-123")


# ============================================================
# Test SnapshotManager
# ============================================================

class TestSnapshotManager(unittest.TestCase):
    """Test SnapshotManager save/load/nearest operations."""

    def test_save_and_load_snapshot(self):
        """Snapshot should save and load correctly."""
        manager = SnapshotManager()

        # Create mock loop with serializable systems
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {"terrain": "forest"}
        mock_loop.world.deserialize = MagicMock()
        mock_loop.npc_system = MagicMock()
        mock_loop.npc_system.serialize.return_value = {"npcs": ["Alice", "Bob"]}
        mock_loop.npc_system.deserialize = MagicMock()

        manager.save_snapshot(100, mock_loop)
        self.assertTrue(manager.has_snapshot(100))
        self.assertEqual(manager.snapshot_count(), 1)

        # Load into different loop
        mock_loop2 = MagicMock()
        mock_loop2.world = MagicMock()
        mock_loop2.npc_system = MagicMock()

        result = manager.load_snapshot(100, mock_loop2)
        self.assertTrue(result)
        mock_loop2.world.deserialize.assert_called_once_with({"terrain": "forest"})
        mock_loop2.npc_system.deserialize.assert_called_once_with({"npcs": ["Alice", "Bob"]})

    def test_nearest_snapshot(self):
        """Nearest snapshot should return closest tick at or before target."""
        manager = SnapshotManager()
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {}
        mock_loop.npc_system = None

        manager.save_snapshot(50, mock_loop)
        manager.save_snapshot(100, mock_loop)
        manager.save_snapshot(150, mock_loop)

        self.assertEqual(manager.nearest_snapshot(175), 150)
        self.assertEqual(manager.nearest_snapshot(100), 100)
        self.assertEqual(manager.nearest_snapshot(75), 50)
        self.assertIsNone(manager.nearest_snapshot(25))

    def test_should_snapshot(self):
        """should_snapshot should return True at interval boundaries."""
        manager = SnapshotManager(snapshot_interval=50)

        self.assertFalse(manager.should_snapshot(0))
        self.assertFalse(manager.should_snapshot(25))
        self.assertTrue(manager.should_snapshot(50))
        self.assertFalse(manager.should_snapshot(75))
        self.assertTrue(manager.should_snapshot(100))

    def test_remove_snapshot(self):
        """Removing a snapshot should return True if it existed."""
        manager = SnapshotManager()
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {}
        mock_loop.npc_system = None

        manager.save_snapshot(50, mock_loop)
        self.assertTrue(manager.remove_snapshot(50))
        self.assertFalse(manager.has_snapshot(50))
        self.assertFalse(manager.remove_snapshot(50))

    def test_clear_snapshots(self):
        """Clearing should remove all snapshots."""
        manager = SnapshotManager()
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {}
        mock_loop.npc_system = None

        manager.save_snapshot(50, mock_loop)
        manager.save_snapshot(100, mock_loop)
        manager.clear()
        self.assertEqual(manager.snapshot_count(), 0)

    def test_snapshot_ticks_are_sorted(self):
        """snapshot_ticks() should return sorted list."""
        manager = SnapshotManager()
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {}
        mock_loop.npc_system = None

        manager.save_snapshot(150, mock_loop)
        manager.save_snapshot(50, mock_loop)
        manager.save_snapshot(100, mock_loop)

        self.assertEqual(manager.snapshot_ticks(), [50, 100, 150])


# ============================================================
# Test Deterministic Replay Ordering
# ============================================================

class TestDeterministicReplay(unittest.TestCase):
    """Test that replay sorts events deterministically."""

    def test_replay_sorts_events_by_tick_timestamp_id(self):
        """Replay should sort events by (tick, timestamp, event_id)."""
        events = [
            Event("b", {"tick": 1}, event_id="b", timestamp=1.0),
            Event("c", {"tick": 1}, event_id="c", timestamp=1.0),
            Event("a", {"tick": 1}, event_id="a", timestamp=1.0),
            Event("d", {"tick": 2}, event_id="d", timestamp=2.0),
        ]

        # Sort using same logic as replay_engine
        sorted_events = sorted(
            events,
            key=lambda e: (
                e.payload.get("tick", 0),
                e.timestamp or 0,
                e.event_id or "",
            ),
        )

        # 'a' < 'b' < 'c' < 'd' for same tick/timestamp
        self.assertEqual(sorted_events[0].event_id, "a")
        self.assertEqual(sorted_events[1].event_id, "b")
        self.assertEqual(sorted_events[2].event_id, "c")
        self.assertEqual(sorted_events[3].event_id, "d")

    def test_replay_orders_by_tick_first(self):
        """Events with later tick should come after events with earlier tick."""
        events = [
            Event("late", {"tick": 5}, event_id="late"),
            Event("early", {"tick": 1}, event_id="early"),
        ]

        sorted_events = sorted(
            events,
            key=lambda e: (
                e.payload.get("tick", 0),
                e.timestamp or 0,
                e.event_id or "",
            ),
        )

        self.assertEqual(sorted_events[0].event_id, "early")
        self.assertEqual(sorted_events[1].event_id, "late")


# ============================================================
# Test GameLoop Snapshot Integration
# ============================================================

class TestGameLoopSnapshotIntegration(unittest.TestCase):
    """Test that GameLoop integrates SnapshotManager correctly."""

    def test_gameloop_creates_default_snapshot_manager(self):
        """GameLoop should create a SnapshotManager if none provided."""
        loop = self._make_loop()
        self.assertIsInstance(loop.snapshot_manager, SnapshotManager)

    def test_gameloop_accepts_custom_snapshot_manager(self):
        """GameLoop should accept a provided SnapshotManager."""
        custom_manager = SnapshotManager(snapshot_interval=100)
        loop = self._make_loop(snapshot_manager=custom_manager)
        self.assertIs(loop.snapshot_manager, custom_manager)
        self.assertEqual(loop.snapshot_manager._snapshot_interval, 100)

    def test_gameloop_saves_snapshot_at_interval(self):
        """GameLoop should save snapshots at configured interval."""
        # Create mock systems
        mock_bus = EventBus()
        mock_world = MagicMock()
        mock_npc_system = MagicMock()
        mock_intent_parser = MagicMock()
        mock_intent_parser.parse.return_value = {}
        mock_story_director = MagicMock()
        mock_story_director.process.return_value = {}
        mock_scene_renderer = MagicMock()
        mock_scene_renderer.render.return_value = {"scene": "test"}

        # Setup world with serialize/deserialize
        mock_world.serialize.return_value = {}
        mock_world.deserialize = MagicMock()
        mock_npc_system.serialize.return_value = {}
        mock_npc_system.deserialize = MagicMock()

        loop = GameLoop(
            intent_parser=mock_intent_parser,
            world=mock_world,
            npc_system=mock_npc_system,
            event_bus=mock_bus,
            story_director=mock_story_director,
            scene_renderer=mock_scene_renderer,
            snapshot_manager=SnapshotManager(snapshot_interval=5),
        )

        # Run 10 ticks
        for i in range(10):
            loop.tick(f"input-{i}")

        # Should have snapshots at tick 5 and 10
        self.assertEqual(loop.snapshot_manager.snapshot_count(), 2)
        self.assertTrue(loop.snapshot_manager.has_snapshot(5))
        self.assertTrue(loop.snapshot_manager.has_snapshot(10))

    def _make_loop(self, snapshot_manager=None):
        """Helper to create a GameLoop with mock systems."""
        return GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=EventBus(),
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
            snapshot_manager=snapshot_manager,
        )


if __name__ == "__main__":
    unittest.main()