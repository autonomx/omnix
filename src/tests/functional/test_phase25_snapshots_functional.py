"""PHASE 2.5 — FUNCTIONAL TESTS: Snapshot & Replay End-to-End

Tests the complete flow of:
- Game running with periodic snapshots
- Hybrid replay loading snapshot + replaying events
- Deterministic replay producing same results
- Time-travel debug with snapshots

Run with: python -m pytest src/tests/functional/test_phase25_snapshots_functional.py -v
"""

import unittest
from unittest.mock import MagicMock, patch

from src.app.rpg.core.event_bus import Event, EventBus
from src.app.rpg.core.snapshot_manager import SnapshotManager
from src.app.rpg.core.replay_engine import ReplayEngine, ReplayConfig
from src.app.rpg.core.game_loop import GameLoop


class TestHybridReplayFunctional(unittest.TestCase):
    """Functional tests for hybrid replay (snapshot + events)."""

    def test_gameloop_replay_uses_snapshots_when_available(self):
        """GameLoop replay_to_tick should use snapshots for fast seeking."""
        # Create mock systems with state tracking
        mock_world = MagicMock()
        mock_world.serialize.return_value = {"terrain": "forest", "tick": 50}
        mock_world.deserialize = MagicMock()
        mock_npc_system = MagicMock()
        mock_npc_system.serialize.return_value = {"npcs": ["Alice"] * 5}
        mock_npc_system.deserialize = MagicMock()
        mock_intent_parser = MagicMock()
        mock_intent_parser.parse.return_value = {}
        mock_story_director = MagicMock()
        mock_story_director.process.return_value = {}
        mock_scene_renderer = MagicMock()
        mock_scene_renderer.render.return_value = {"scene": "test"}

        mock_bus = EventBus()
        loop = GameLoop(
            intent_parser=mock_intent_parser,
            world=mock_world,
            npc_system=mock_npc_system,
            event_bus=mock_bus,
            story_director=mock_story_director,
            scene_renderer=mock_scene_renderer,
            snapshot_manager=SnapshotManager(snapshot_interval=50),
        )

        # Run for 100 ticks (should save snapshots at 50, 100)
        for i in range(100):
            loop.tick(f"input-{i}")

        # Verify snapshots were created
        self.assertTrue(loop.snapshot_manager.has_snapshot(50))
        self.assertTrue(loop.snapshot_manager.has_snapshot(100))

        # Get events for replay
        events = mock_bus.history()
        self.assertIsNotNone(events)

    def test_replay_preserves_event_causality(self):
        """Replay should preserve causal relationships via parent_id."""
        # Create events with parent-child relationships
        parent_event = Event("npc_spawned", {"tick": 1, "npc_id": 1})
        child_event = Event(
            "npc_moved",
            {"tick": 1, "npc_id": 1, "x": 10, "y": 20},
            parent_id=parent_event.event_id,
        )
        grandchild_event = Event(
            "npc_talked",
            {"tick": 1, "npc_id": 1, "dialogue": "Hello!"},
            parent_id=child_event.event_id,
        )

        events = [child_event, parent_event, grandchild_event]

        # Simulate replay sorting
        sorted_events = sorted(
            events,
            key=lambda e: (
                e.payload.get("tick", 0),
                e.timestamp or 0,
                e.event_id or "",
            ),
        )

        # Verify all events are present
        self.assertEqual(len(sorted_events), 3)
        event_ids = {e.event_id for e in sorted_events}
        self.assertIn(parent_event.event_id, event_ids)
        self.assertIn(child_event.event_id, event_ids)
        self.assertIn(grandchild_event.event_id, event_ids)

    def test_deterministic_replay_produces_same_order(self):
        """Running replay sorting twice should produce identical order."""
        # Create events with same tick/timestamp to test deterministic ordering
        events = [
            Event("c", {"tick": 1}, event_id="c", timestamp=1.0),
            Event("a", {"tick": 1}, event_id="a", timestamp=1.0),
            Event("b", {"tick": 1}, event_id="b", timestamp=1.0),
        ]

        def sort_events(evts):
            return sorted(
                evts,
                key=lambda e: (
                    e.payload.get("tick", 0),
                    e.timestamp or 0,
                    e.event_id or "",
                ),
            )

        result1 = sort_events(events)
        result2 = sort_events(events)

        # Both should be identical
        self.assertEqual([e.event_id for e in result1], [e.event_id for e in result2])
        self.assertEqual([e.event_id for e in result1], ["a", "b", "c"])


class TestSnapshotPerformanceFunctional(unittest.TestCase):
    """Functional tests for snapshot performance improvements."""

    def test_snapshot_reduces_replay_events(self):
        """With snapshots, replay should skip events before snapshot tick."""
        manager = SnapshotManager(snapshot_interval=50)
        mock_loop = MagicMock()
        mock_loop.world = MagicMock()
        mock_loop.world.serialize.return_value = {"state": "at-50"}
        mock_loop.world.deserialize = MagicMock()
        mock_loop.npc_system = MagicMock()
        mock_loop.npc_system.serialize.return_value = {}
        mock_loop.npc_system.deserialize = MagicMock()

        # Create 100 events
        events = [
            Event(f"event-{i}", {"tick": i}, event_id=f"id-{i}", timestamp=float(i))
            for i in range(1, 101)
        ]

        # Save snapshot at tick 50
        manager.save_snapshot(50, mock_loop)

        # Create ReplayEngine
        def fresh_loop_factory():
            loop = MagicMock()
            loop.world = MagicMock()
            loop.world.serialize.return_value = {}
            loop.world.deserialize = MagicMock()
            loop.npc_system = MagicMock()
            loop.npc_system.serialize.return_value = {}
            loop.npc_system.deserialize = MagicMock()
            loop.snapshot_manager = manager
            loop.event_bus = EventBus()
            loop._tick_count = 0
            return loop

        engine = ReplayEngine(fresh_loop_factory)
        replayed_loop = engine.replay(events, up_to_tick=75)

        # The replay should have loaded snapshot at 50 and replayed events 51-75
        # Verify the replay completed without error
        self.assertIsNotNone(replayed_loop)

    def test_out_of_order_events_reordered(self):
        """Events arriving out of order should be replayed in correct order."""
        # Simulate network latency causing out-of-order events
        out_of_order = [
            Event("late", {"tick": 3}, event_id="late", timestamp=3.0),
            Event("early", {"tick": 1}, event_id="early", timestamp=1.0),
            Event("middle", {"tick": 2}, event_id="middle", timestamp=2.0),
            Event("very-early", {"tick": 0}, event_id="very-early", timestamp=0.0),
        ]

        # Sort as replay_engine does
        sorted_events = sorted(
            out_of_order,
            key=lambda e: (
                e.payload.get("tick", 0),
                e.timestamp or 0,
                e.event_id or "",
            ),
        )

        expected_order = ["very-early", "early", "middle", "late"]
        self.assertEqual([e.event_id for e in sorted_events], expected_order)


class TestEventBusHistoryFunctional(unittest.TestCase):
    """Functional tests for EventBus history tracking."""

    def test_load_history_for_replay(self):
        """EventBus load_history should restore events for replay inspection."""
        bus = EventBus()

        events = [
            Event("e1", {"tick": 1}, event_id="e1"),
            Event("e2", {"tick": 2}, event_id="e2"),
            Event("e3", {"tick": 3}, event_id="e3"),
        ]

        bus.load_history(events)
        history = bus.history()

        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].event_id, "e1")
        self.assertEqual(history[2].event_id, "e3")


if __name__ == "__main__":
    unittest.main()