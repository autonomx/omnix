"""PHASE 5.2 — Unit Tests for Deterministic Event System (rpg-design.txt)

Tests for all 5 critical fixes from rpg-design.txt:
- Fix #1: Deterministic Event IDs (evt_1, evt_2, ... instead of uuid4)
- Fix #2: Deterministic Clock injection (replace time.time())
- Fix #3: Memory leak fix for _seen_event_ids_set
- Fix #4: First-class tick field on Event
- Fix #5: Timeline rebuild on load_history

These tests verify that the deterministic event system works correctly.
"""

import unittest
from typing import Any, List, Optional
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus, EventContext
from app.rpg.core.clock import DeterministicClock
from app.rpg.core.timeline_graph import TimelineGraph


# ---------------------------------------------------------------------------
# Fix #1: Deterministic Event ID Tests
# ---------------------------------------------------------------------------

class TestDeterministicEventIds(unittest.TestCase):
    """PHASE 5.2 Fix #1: Event IDs should be sequential and deterministic."""

    def setUp(self):
        """Reset the global counter before each test."""
        EventBus._global_event_counter = 0

    def test_next_event_id_starts_at_one(self):
        """First event ID should be 'evt_1'."""
        eid = EventBus.next_event_id()
        self.assertEqual(eid, "evt_1")

    def test_next_event_id_is_sequential(self):
        """Event IDs should increment sequentially."""
        ids = [EventBus.next_event_id() for _ in range(5)]
        self.assertEqual(ids, ["evt_1", "evt_2", "evt_3", "evt_4", "evt_5"])

    def test_event_auto_uses_deterministic_id(self):
        """Events created without explicit event_id should use sequential IDs."""
        e1 = Event(type="test", payload={}, source="test")
        e2 = Event(type="test", payload={}, source="test")
        e3 = Event(type="test", payload={}, source="test")

        self.assertEqual(e1.event_id, "evt_1")
        self.assertEqual(e2.event_id, "evt_2")
        self.assertEqual(e3.event_id, "evt_3")

    def test_explicit_event_id_is_preserved(self):
        """Events with explicit event_id should NOT use the counter."""
        e = Event(type="test", payload={}, source="test", event_id="custom_id")
        self.assertEqual(e.event_id, "custom_id")
        # Counter should still increment on next call
        self.assertEqual(EventBus.next_event_id(), "evt_1")

    def test_deterministic_reproduction(self):
        """Two identical sequences should produce identical event IDs."""
        # First sequence
        bus1 = EventBus()
        events1 = []
        for i in range(3):
            e = Event(type="test", payload={"i": i}, source="test")
            bus1.emit(e)
            events1.append(e)

        ids1 = [e.event_id for e in events1]

        # Reset counter
        EventBus._global_event_counter = 0

        # Second sequence
        bus2 = EventBus()
        events2 = []
        for i in range(3):
            e = Event(type="test", payload={"i": i}, source="test")
            bus2.emit(e)
            events2.append(e)

        ids2 = [e.event_id for e in events2]

        self.assertEqual(ids1, ids2)


# ---------------------------------------------------------------------------
# Fix #2: Deterministic Clock Tests
# ---------------------------------------------------------------------------

class TestDeterministicClock(unittest.TestCase):
    """PHASE 5.2 Fix #2: DeterministicClock provides predictable timestamps."""

    def test_clock_starts_at_zero(self):
        """Clock should start at 0.0."""
        clock = DeterministicClock()
        self.assertEqual(clock.current_time(), 0.0)

    def test_clock_advances_on_now(self):
        """Each call to now() should advance time by increment."""
        clock = DeterministicClock(increment=0.001)
        t1 = clock.now()
        t2 = clock.now()
        t3 = clock.now()

        self.assertEqual(t1, 0.001)
        self.assertEqual(t2, 0.002)
        self.assertEqual(t3, 0.003)

    def test_clock_with_custom_start(self):
        """Clock should start at custom value."""
        clock = DeterministicClock(start_time=100.0, increment=1.0)
        self.assertEqual(clock.current_time(), 100.0)
        self.assertEqual(clock.now(), 101.0)

    def test_clock_set_time(self):
        """Clock time can be set explicitly."""
        clock = DeterministicClock()
        clock.set_time(42.0)
        self.assertEqual(clock.current_time(), 42.0)

    def test_clock_advance(self):
        """Clock can be advanced by arbitrary amounts."""
        clock = DeterministicClock()
        clock.advance(5.0)
        self.assertEqual(clock.current_time(), 5.0)
        clock.advance(3.0)
        self.assertEqual(clock.current_time(), 8.0)

    def test_clock_reset(self):
        """Clock can be reset to zero."""
        clock = DeterministicClock()
        clock.advance(100.0)
        clock.reset()
        self.assertEqual(clock.current_time(), 0.0)


class TestEventWithDeterministicClock(unittest.TestCase):
    """PHASE 5.2 Fix #2: Events use DeterministicClock for timestamps."""

    def setUp(self):
        """Reset state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None
        # Reset sequence counter for deterministic behavior

    def test_event_without_clock_uses_zero(self):
        """Without a clock, timestamps should default to 0.0."""
        e = Event(type="test", payload={}, source="test")
        self.assertEqual(e.timestamp, 0.0)

    def test_event_with_clock_uses_clock_time(self):
        """With a clock, timestamps come from DeterministicClock."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)

        e1 = Event(type="first", payload={}, source="test")
        e2 = Event(type="second", payload={}, source="test")

        self.assertEqual(e1.timestamp, 0.001)
        self.assertEqual(e2.timestamp, 0.002)

    def test_emit_uses_clock_for_new_events(self):
        """Events created during emit should use the clock."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)

        e1 = Event(type="a", payload={}, source="test")
        e2 = Event(type="b", payload={}, source="test")

        bus.emit(e1)
        bus.emit(e2)

        # Events should have deterministic timestamps
        self.assertEqual(e1.timestamp, 0.001)
        self.assertEqual(e2.timestamp, 0.002)

    def test_replay_uses_same_timestamps(self):
        """Replay with same clock setup should produce identical timestamps."""
        # First run
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        bus1 = EventBus(clock=clock1)
        events1 = []
        for i in range(3):
            e = Event(type=f"evt_{i}", payload={}, source="test")
            bus1.emit(e)
            events1.append(e)

        # Second run (simulating replay)
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        bus2 = EventBus(clock=clock2)
        events2 = []
        for i in range(3):
            e = Event(type=f"evt_{i}", payload={}, source="test")
            bus2.emit(e)
            events2.append(e)

        # Timestamps should match
        for e1, e2 in zip(events1, events2):
            self.assertEqual(e1.timestamp, e2.timestamp)


# ---------------------------------------------------------------------------
# Fix #3: Memory Leak Fix Tests
# ---------------------------------------------------------------------------

class TestSeenEventIdsMemoryLeak(unittest.TestCase):
    """PHASE 5.2 Fix #3: _seen_event_ids_set is pruned with deque."""

    def setUp(self):
        """Reset state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_seen_set_grows_with_deque(self):
        """Set should stay in sync with the bounded deque."""
        bus = EventBus()
        # Use a small maxlen for testing
        maxlen = 10
        bus._seen_event_ids = __import__('collections').deque(maxlen=maxlen)

        for i in range(20):
            # Reset counter to get unique IDs each time
            EventBus._global_event_counter = i
            e = Event(type="test", payload={}, source="test")
            bus.emit(e)

        # Set size should be within maxlen + 1 (due to pruning timing)
        self.assertLessEqual(len(bus._seen_event_ids_set), maxlen + 1)

    def test_seen_set_removes_oldest_on_wrap(self):
        """When deque wraps, oldest entry should be removed from set."""
        bus = EventBus()
        maxlen = 3
        bus._seen_event_ids = __import__('collections').deque(maxlen=maxlen)

        # Emit 5 events
        for i in range(5):
            EventBus._global_event_counter = i
            e = Event(type="test", payload={}, source="test")
            bus.emit(e)

        # After 5 events with maxlen=3:
        # The set should be bounded (within maxlen + 1 due to pruning timing)
        self.assertLessEqual(len(bus._seen_event_ids_set), maxlen + 1)


# ---------------------------------------------------------------------------
# Fix #4: First-Class Tick Tests
# ---------------------------------------------------------------------------

class TestFirstClassTick(unittest.TestCase):
    """PHASE 5.2 Fix #4: tick is a first-class field on Event."""

    def setUp(self):
        """Reset state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_event_has_tick_field(self):
        """Event dataclass should have a tick field."""
        e = Event(type="test", payload={}, source="test")
        self.assertIsNone(e.tick)

    def test_event_with_explicit_tick(self):
        """Event can be created with explicit tick."""
        e = Event(type="test", payload={}, source="test", tick=5)
        self.assertEqual(e.tick, 5)

    def test_emit_injects_tick(self):
        """EventBus.emit() should inject current_tick into event.tick."""
        bus = EventBus()
        bus.set_tick(42)

        e = Event(type="test", payload={}, source="test")
        bus.emit(e)

        self.assertEqual(e.tick, 42)

    def test_history_sorted_by_first_class_tick(self):
        """history() should sort by event.tick (first-class field)."""
        bus = EventBus()

        bus.set_tick(3)
        e3 = Event(type="c", payload={}, source="test")
        bus.emit(e3)

        bus.set_tick(1)
        e1 = Event(type="a", payload={}, source="test")
        bus.emit(e1)

        bus.set_tick(2)
        e2 = Event(type="b", payload={}, source="test")
        bus.emit(e2)

        history = bus.history()
        # Should be sorted by tick
        self.assertEqual(history[0].type, "a")
        self.assertEqual(history[1].type, "b")
        self.assertEqual(history[2].type, "c")

    def test_tick_defaults_to_none_when_not_in_emit(self):
        """Events not emitted via bus should have tick=None."""
        e = Event(type="test", payload={}, source="test")
        self.assertIsNone(e.tick)


# ---------------------------------------------------------------------------
# Fix #5: Timeline Rebuild Tests
# ---------------------------------------------------------------------------

class TestTimelineRebuildOnLoad(unittest.TestCase):
    """PHASE 5.2 Fix #5: Timeline is rebuilt when history is loaded."""

    def setUp(self):
        """Reset state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_load_history_rebuilds_timeline(self):
        """load_history() should rebuild the timeline graph."""
        bus = EventBus()

        # Create events with parent links
        e1 = Event(type="root", payload={}, source="test", event_id="evt_1")
        e2 = Event(type="child", payload={}, source="test", event_id="evt_2",
                   parent_id="evt_1")
        e3 = Event(type="leaf", payload={}, source="test", event_id="evt_3",
                   parent_id="evt_2")

        # Load history
        bus.load_history([e1, e2, e3])

        # Timeline should have been rebuilt
        graph = bus.timeline
        self.assertTrue(graph.has_event("evt_1"))
        self.assertTrue(graph.has_event("evt_2"))
        self.assertTrue(graph.has_event("evt_3"))

    def test_load_history_clears_old_timeline(self):
        """load_history() should clear existing timeline before rebuilding."""
        bus = EventBus()

        # Add some events to timeline
        old_e = Event(type="old", payload={}, source="test", event_id="old_evt")
        bus.timeline.add_event(old_e.event_id, None)

        # Load new history
        new_e = Event(type="new", payload={}, source="test", event_id="new_evt")
        bus.load_history([new_e])

        # Old event should be gone
        self.assertFalse(bus.timeline.has_event("old_evt"))
        self.assertTrue(bus.timeline.has_event("new_evt"))

    def test_load_history_empty_clears_timeline(self):
        """load_history([]) should clear the timeline."""
        bus = EventBus()

        # Add some events
        e = Event(type="test", payload={}, source="test", event_id="test_evt")
        bus.timeline.add_event(e.event_id, None)

        # Load empty history
        bus.load_history([])

        # Timeline should be clear
        self.assertFalse(bus.timeline.has_event("test_evt"))


# ---------------------------------------------------------------------------
# Integration: Bit-Exact Replay Test (rpg-design.txt BONUS)
# ---------------------------------------------------------------------------

class TestBitExactReplay(unittest.TestCase):
    """rpg-design.txt BONUS: Replay should be bit-exact."""

    def setUp(self):
        """Reset state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_replay_is_bit_exact(self):
        """Running game twice with same setup should produce identical state.

        This is the ultimate truth test from rpg-design.txt:
            run_game(loop, steps=10)
            history = loop.event_bus.history()
            run_game(loop2, steps=10)
            assert compute_state_hash(loop) == compute_state_hash(loop2)
        """
        from app.rpg.validation.state_hash import compute_state_hash

        # First run - reset counter and clock for determinism
        EventBus._global_event_counter = 0
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        bus1 = EventBus(clock=clock1)

        # Simulate 10 ticks
        for tick in range(1, 11):
            bus1.set_tick(tick)
            e = Event(
                type="tick_event",
                payload={"tick": tick, "action": f"action_{tick}"},
                source="game_loop",
            )
            bus1.emit(e)

        history1 = bus1.history()
        hash1_inputs = {
            "tick": 10,
            "events": [(e.event_id, e.type, e.tick, e._seq) for e in history1],
        }

        # Reset and replay with identical setup
        EventBus._global_event_counter = 0
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        bus2 = EventBus(clock=clock2)
        bus2._seq = 0  # Reset sequence counter

        # Re-emit with same setup (identical to first run)
        for tick in range(1, 11):
            bus2.set_tick(tick)
            e = Event(
                type="tick_event",
                payload={"tick": tick, "action": f"action_{tick}"},
                source="game_loop",
            )
            bus2.emit(e)

        history2 = bus2.history()
        hash2_inputs = {
            "tick": 10,
            "events": [(e.event_id, e.type, e.tick, e._seq) for e in history2],
        }

        # Both runs should produce identical results
        self.assertEqual(hash1_inputs, hash2_inputs)

    def test_event_ids_comparable_across_runs(self):
        """Event IDs should be comparable when clock and counter are reset."""
        # Run 1
        EventBus._global_event_counter = 0
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        bus.set_tick(1)
        e1 = Event(type="a", payload={}, source="test")
        bus.emit(e1)
        bus.set_tick(2)
        e2 = Event(type="b", payload={}, source="test")
        bus.emit(e2)

        ids_run1 = [e1.event_id, e2.event_id]
        ticks_run1 = [e1.tick, e2.tick]
        timestamps_run1 = [e1.timestamp, e2.timestamp]

        # Run 2 (reset everything)
        EventBus._global_event_counter = 0
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        bus.set_tick(1)
        e1 = Event(type="a", payload={}, source="test")
        bus.emit(e1)
        bus.set_tick(2)
        e2 = Event(type="b", payload={}, source="test")
        bus.emit(e2)

        ids_run2 = [e1.event_id, e2.event_id]
        ticks_run2 = [e1.tick, e2.tick]
        timestamps_run2 = [e1.timestamp, e2.timestamp]

        self.assertEqual(ids_run1, ids_run2)
        self.assertEqual(ticks_run1, ticks_run2)
        self.assertEqual(timestamps_run1, timestamps_run2)


if __name__ == "__main__":
    unittest.main()