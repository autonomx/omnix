"""PHASE 5.2 — Regression Tests for Deterministic Event System (rpg-design.txt)

These tests ensure that the deterministic event system changes don't break
existing functionality and that previously fixed issues stay fixed.

Tests cover:
- Backward compatibility with existing Event usage
- EventBus behavior with legacy code patterns
- Replay engine compatibility with old event formats
- Memory stability under long-running scenarios
"""

import unittest
from collections import deque
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus, EventContext
from app.rpg.core.clock import DeterministicClock
from app.rpg.core.replay_engine import ReplayEngine, ReplayConfig


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
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_event_id_format_stable(self):
        """Event IDs should follow the expected format."""
        eid = EventBus.next_event_id()
        self.assertTrue(eid.startswith("evt_"))

    def test_event_id_uniqueness(self):
        """Event IDs should be unique within a session."""
        EventBus._global_event_counter = 0
        ids = set()
        for _ in range(100):
            eid = EventBus.next_event_id()
            self.assertNotIn(eid, ids)
            ids.add(eid)

    def test_event_with_none_id_gets_auto_id(self):
        """Events with None event_id should receive auto-generated ID."""
        e = Event(type="test", payload={}, source="test", event_id=None)
        self.assertIsNotNone(e.event_id)


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


if __name__ == "__main__":
    unittest.main()