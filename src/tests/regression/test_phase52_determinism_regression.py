"""PHASE 5.2 — Regression Tests for Deterministic Event System (rpg-design.txt)

These tests ensure that the deterministic event system changes don't break
existing functionality and that previously fixed issues stay fixed.

Tests cover:
- Backward compatibility with existing Event usage
- EventBus behavior with legacy code patterns
- Replay engine compatibility with old event formats
- Memory stability under long-running scenarios
"""

import os
import sys
import unittest
from collections import deque
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.clock import DeterministicClock
from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.event_bus import Event, EventBus, EventContext
from app.rpg.core.replay_engine import ReplayConfig, ReplayEngine

# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    """PHASE 5.2 Regression: Existing code should continue to work."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_event_without_clock_works(self):
        """Events should work without a DeterministicClock."""
        e = Event(type="test", payload={"key": "value"}, source="test_system")
        # event_id and timestamp assigned during emit, not construction
        self.assertIsNone(e.event_id)  # Assigned by emit
        self.assertIsNone(e.timestamp)  # Assigned by emit
        # After emit, they should be populated
        bus = EventBus()
        bus.emit(e)
        self.assertIsNotNone(e.event_id)
        self.assertIsNotNone(e.timestamp)

    def test_eventbus_without_clock_works(self):
        """EventBus should work without a DeterministicClock."""
        bus = EventBus()
        e = Event(type="test", payload={}, source="test")
        bus.emit(e)
        
        events = bus.collect()
        self.assertEqual(len(events), 1)

    def test_explicit_event_id_still_works(self):
        """Explicit event_id should still be honored."""
        e = Event(type="test", payload={}, source="test", event_id="my_custom_id")
        bus = EventBus()
        bus.emit(e)
        
        history = bus.history()
        self.assertEqual(history[0].event_id, "my_custom_id")

    def test_event_with_all_fields_explicit_works(self):
        """Events with all fields explicitly set should work correctly."""
        e = Event(
            type="custom_type",
            payload={"custom": "data"},
            source="custom_source",
            event_id="custom_id",
            timestamp=12345.0,
            parent_id="parent_id",
            tick=42,
        )
        bus = EventBus()
        bus.emit(e)
        
        history = bus.history()
        self.assertEqual(history[0].type, "custom_type")
        self.assertEqual(history[0].payload["custom"], "data")
        # tick gets overwritten by bus.set_tick which is None, so original preserved
        self.assertEqual(history[0].parent_id, "parent_id")

    def test_enforcement_mode_still_works(self):
        """EventBus enforce mode should still work."""
        bus = EventBus(enforce=True)
        
        # Should raise error for events without source
        with self.assertRaises(RuntimeError):
            bus.emit(Event(type="test", payload={}))


# ---------------------------------------------------------------------------
# Legacy Code Pattern Tests
# ---------------------------------------------------------------------------

class TestLegacyPatterns(unittest.TestCase):
    """PHASE 5.2 Regression: Legacy code patterns should still work."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_payload_tick_still_populated(self):
        """Events should still have tick in payload for legacy compatibility."""
        bus = EventBus()
        bus.set_tick(5)
        e = Event(type="test", payload={}, source="test")
        bus.emit(e)
        
        # event.tick (first-class field) should be set
        self.assertEqual(e.tick, 5)
        # The cloned event in history has payload tick
        history = bus.history()
        self.assertIn("tick", history[0].payload)

    def test_history_sorting_backward_compatible(self):
        """History sorting should handle events with tick in payload."""
        bus = EventBus()
        
        # Events with tick only in payload (old style)
        bus.set_tick(2)
        e2 = Event(type="b", payload={"tick": 2}, source="test")
        bus.emit(e2)
        
        bus.set_tick(1)
        e1 = Event(type="a", payload={"tick": 1}, source="test")
        bus.emit(e1)
        
        history = bus.history()
        # Should be sorted correctly
        self.assertEqual(history[0].type, "a")
        self.assertEqual(history[1].type, "b")

    def test_replay_engine_backward_compatible(self):
        """ReplayEngine should work with events from both old and new patterns."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        
        # Record events
        for tick in range(1, 4):
            bus.set_tick(tick)
            e = Event(type=f"event_{tick}", payload={"tick": tick}, source="test")
            bus.emit(e)
        
        history = bus.history()
        
        # Reset
        EventBus._global_event_counter = 0
        
        # Replay via load_history (legacy path)
        replay_bus = EventBus(clock=clock)
        replay_bus.load_history(history)
        
        # Events should be accessible
        replayed = replay_bus.history()
        self.assertEqual(len(replayed), len(history))


# ---------------------------------------------------------------------------
# Memory Stability Tests
# ---------------------------------------------------------------------------

class TestMemoryStability(unittest.TestCase):
    """PHASE 5.2 Regression: Memory should remain stable under load."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_seen_ids_set_bounded(self):
        """The seen IDs set should remain bounded over many events."""
        bus = EventBus()
        bus._seen_event_ids = deque(maxlen=100)
        
        initial_set_size = len(bus._seen_event_ids_set)
        
        # Emit many events
        for i in range(500):
            EventBus._global_event_counter = i
            e = Event(type="test", payload={}, source="test")
            bus.emit(e)
        
        # Set should have grown but be bounded
        self.assertLessEqual(len(bus._seen_event_ids_set), 101)  # maxlen + 1 for current

    def test_history_bounded(self):
        """Event history should remain bounded."""
        bus = EventBus()
        bus._max_history = 50
        
        for tick in range(1, 200):
            bus.set_tick(tick)
            e = Event(type="test", payload={"tick": tick}, source="test")
            bus.emit(e)
        
        # History should not exceed max
        self.assertLessEqual(len(bus._history), bus._max_history)

    def test_reset_clears_all_state(self):
        """reset() should clear all accumulated state."""
        bus = EventBus()
        
        # Generate some state
        for i in range(10):
            e = Event(type="test", payload={}, source="test")
            bus.emit(e)
        
        bus.reset()
        
        # All state should be cleared
        self.assertEqual(bus.pending_count, 0)
        self.assertEqual(len(bus.history()), 0)
        self.assertEqual(bus._current_tick, None)
        self.assertEqual(len(bus._seen_event_ids), 0)
        self.assertEqual(len(bus._seen_event_ids_set), 0)


# ---------------------------------------------------------------------------
# Event ID Stability Tests
# ---------------------------------------------------------------------------

class TestEventIdStability(unittest.TestCase):
    """PHASE 5.2 Regression: Event IDs should be stable and predictable."""

    def setUp(self):
        """No class-global reset needed; determinism is instance-based now."""
        pass

    def test_event_id_format_stable(self):
        """Event IDs should follow the expected format after emit."""
        bus = EventBus()
        e = Event(type="test", payload={}, source="test")
        bus.emit(e)
        self.assertTrue(e.event_id.startswith("evt_"))

    def test_event_id_uniqueness(self):
        """Event IDs should be unique within a session."""
        bus = EventBus()
        ids = set()
        for _ in range(100):
            e = Event(type="test", payload={"i": _}, source="test")
            bus.emit(e)
            self.assertNotIn(e.event_id, ids)
            ids.add(e.event_id)

    def test_event_with_none_id_gets_auto_id(self):
        """Events with None event_id should receive auto-generated ID after emit."""
        e = Event(type="test", payload={}, source="test", event_id=None)
        self.assertIsNone(e.event_id)  # Not assigned yet
        bus = EventBus()
        bus.emit(e)
        self.assertIsNotNone(e.event_id)  # Assigned by emit


# ---------------------------------------------------------------------------
# Integration Regression Tests
# ---------------------------------------------------------------------------

class TestIntegrationRegression(unittest.TestCase):
    """PHASE 5.2 Regression: Integration functionality should be preserved."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_event_context_still_works(self):
        """EventContext should still provide causal linking."""
        bus = EventBus()
        
        bus.set_tick(1)
        root = Event(type="root", payload={}, source="test")
        bus.emit(root)
        
        ctx = EventContext(parent_id=root.event_id)
        child = Event(type="child", payload={}, source="test")
        bus.emit(child, context=ctx)
        
        history = bus.history()
        self.assertEqual(history[1].parent_id, history[0].event_id)

    def test_multiple_emits_per_tick(self):
        """Multiple emits within the same tick should work correctly."""
        bus = EventBus()
        bus.set_tick(1)
        
        events = []
        for i in range(5):
            e = Event(type=f"event_{i}", payload={"i": i}, source="test")
            bus.emit(e)
            events.append(e)
        
        history = bus.history()
        self.assertEqual(len(history), 5)
        
        # All events should have same tick
        for h in history:
            self.assertEqual(h.tick, 1)

    def test_cross_tick_consistency(self):
        """Events across ticks should maintain correct ordering."""
        bus = EventBus()
        
        # Tick 1
        bus.set_tick(1)
        e1 = Event(type="first", payload={}, source="test")
        bus.emit(e1)
        
        # Tick 2
        bus.set_tick(2)
        e2 = Event(type="second", payload={}, source="test")
        bus.emit(e2)
        
        # Tick 3
        bus.set_tick(3)
        e3 = Event(type="third", payload={}, source="test")
        bus.emit(e3)
        
        history = bus.history()
        self.assertEqual([h.type for h in history], ["first", "second", "third"])

    def test_peek_and_collect_consistency(self):
        """peek() and collect() should be consistent."""
        bus = EventBus()
        
        e1 = Event(type="first", payload={}, source="test")
        e2 = Event(type="second", payload={}, source="test")
        bus.emit(e1)
        bus.emit(e2)
        
        # peek should return the same events as collected
        peeked = bus.peek()
        collected = bus.collect()
        
        self.assertEqual(len(peeked), len(collected))
        self.assertEqual([p.type for p in peeked], [c.type for c in collected])

    def test_debug_logging_still_works(self):
        """Debug mode should still log events."""
        import io
        from contextlib import redirect_stdout
        
        bus = EventBus(debug=True)
        
        # Capture stdout
        f = io.StringIO()
        with redirect_stdout(f):
            e = Event(type="debug_test", payload={"x": 1}, source="test")
            bus.emit(e)
        
        output = f.getvalue()
        self.assertIn("debug_test", output)


# ---------------------------------------------------------------------------
# Phase 52 — Deterministic Replay Hardening Regression Tests (rpg-design.txt)
# ---------------------------------------------------------------------------

class TestPhase52DeterministicReplayRegression(unittest.TestCase):
    """PHASE 5.2: Deterministic replay hardening regression tests."""

    def test_seen_event_ids_set_stays_in_sync_with_bounded_deque(self):
        """The seen IDs set should stay in sync with the bounded deque."""
        from collections import deque
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=10))
        bus._seen_event_ids.clear()
        bus._seen_event_ids_set.clear()
        bus._seen_event_ids = deque(maxlen=3)

        for i in range(5):
            bus.set_tick(i + 1)
            bus.emit(Event(type="x", payload={"i": i}, source="sys"))

        self.assertEqual(set(bus._seen_event_ids), bus._seen_event_ids_set)
        self.assertLessEqual(len(bus._seen_event_ids), 3)

    def test_load_history_restores_seq_and_tick_state(self):
        """load_history should restore sequence and tick state correctly."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=11))
        bus.set_tick(1)
        e1 = Event(type="start", payload={}, source="sys")
        bus.emit(e1)
        bus.set_tick(2)
        e2 = Event(type="move", payload={"x": 1}, source="player", parent_id=e1.event_id)
        bus.emit(e2)

        history = bus.history()

        bus2 = EventBus(clock=DeterministicClock(start_time=0.0, increment=0.001),
                       determinism=DeterminismConfig(seed=11))
        bus2.load_history(history)

        self.assertIn(e1.event_id, bus2.timeline.nodes)
        self.assertIn(e2.event_id, bus2.timeline.nodes)
        self.assertGreaterEqual(bus2._seq, max(getattr(e, "_seq", 0) for e in history) + 1)
        self.assertEqual(bus2._current_tick, 2)

    def test_replay_mode_flag_resets_after_exception(self):
        """Replay mode flag should be reset even if replay throws."""
        from app.rpg.core.replay_engine import ReplayEngine

        class DummyLoop:
            def __init__(self):
                self.mode = "live"
                self._tick_count = 0
                self.event_bus = EventBus(
                    clock=DeterministicClock(start_time=0.0, increment=0.001),
                    determinism=DeterminismConfig(seed=12),
                )
            def set_mode(self, mode):
                self.mode = mode

        # Create a DummyLoop instance that the factory will return
        loop_instance = DummyLoop()
        replay = ReplayEngine(lambda: loop_instance)

        def boom(loop, event):
            raise RuntimeError("boom")

        replay._apply_event = lambda loop, event: boom(loop, event)

        try:
            replay.replay([Event(type="x", payload={}, source="sys", event_id="evt_fixed", timestamp=0.1, tick=1)])
        except RuntimeError:
            pass

        # The loop instance should have been reset to live mode
        self.assertEqual(loop_instance.mode, "live")
        self.assertFalse(loop_instance.event_bus._determinism.replay_mode)

    def test_bus_usable_after_replay_mode_exception(self):
        """EventBus should remain usable after a replay-mode failure."""
        bus = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=13),
        )

        bus.set_replay_mode(True)

        with self.assertRaises(RuntimeError):
            bus.emit(
                Event(type="x", payload={}, source="sys", event_id=None, timestamp=1.0),
                replay=True,
            )

        bus.set_replay_mode(False)
        bus.emit(Event(type="y", payload={}, source="sys"))

        self.assertEqual(len(bus.history()), 1)
        self.assertEqual(bus.history()[0].type, "y")
        self.assertFalse(bus.is_replay_mode())

    def test_identity_not_derived_from_payload_tick_duplication(self):
        """Identity should use top-level tick, not depend on payload['tick'] duplication semantics."""
        seed = 88

        bus1 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus1.set_tick(5)
        e1 = Event(type="move", payload={"x": 1}, source="player")
        bus1.emit(e1)

        bus2 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        e2 = Event(type="move", payload={"x": 1}, source="player", tick=5)
        bus2.emit(e2)

        self.assertEqual(e1.event_id, e2.event_id)

    def test_loaded_history_preserves_identity_stability(self):
        """Loading history should not alter existing deterministic IDs."""
        seed = 99
        bus1 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus1.set_tick(1)
        e1 = Event(type="start", payload={"zone": "town"}, source="sys")
        bus1.emit(e1)
        original_id = e1.event_id
        history = bus1.history()

        bus2 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus2.load_history(history)

        self.assertEqual(bus2.history()[0].event_id, original_id)


if __name__ == "__main__":
    unittest.main()
