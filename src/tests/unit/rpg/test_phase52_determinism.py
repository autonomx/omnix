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
# Fix #1: Deterministic Event ID Tests (Seeded Determinism)
# ---------------------------------------------------------------------------

from app.rpg.core.determinism import (
    DeterminismConfig,
    SeededRNG,
    stable_json,
    compute_deterministic_event_id,
)


class TestDeterministicEventIds(unittest.TestCase):
    """PHASE 5.2 Fix #1: Event IDs should be derived from causal history."""

    def test_compute_deterministic_event_id_is_deterministic(self):
        """Same inputs should produce same event IDs."""
        id1 = compute_deterministic_event_id(
            seed=42,
            event_type="attack",
            payload={"target": "goblin"},
            source="npc",
            parent_id=None,
            tick=1,
            seq=0,
        )
        id2 = compute_deterministic_event_id(
            seed=42,
            event_type="attack",
            payload={"target": "goblin"},
            source="npc",
            parent_id=None,
            tick=1,
            seq=0,
        )
        self.assertEqual(id1, id2)

    def test_event_id_format_starts_with_evt(self):
        """Event IDs should follow the 'evt_' format."""
        eid = compute_deterministic_event_id(
            seed=0, event_type="test", payload={}, source="sys",
            parent_id=None, tick=1, seq=0,
        )
        self.assertTrue(eid.startswith("evt_"))

    def test_different_seed_changes_event_id(self):
        """Different seeds should produce different event IDs."""
        id1 = compute_deterministic_event_id(
            seed=1, event_type="attack", payload={}, source="npc",
            parent_id=None, tick=1, seq=0,
        )
        id2 = compute_deterministic_event_id(
            seed=2, event_type="attack", payload={}, source="npc",
            parent_id=None, tick=1, seq=0,
        )
        self.assertNotEqual(id1, id2)

    def test_different_type_changes_event_id(self):
        """Different event types should produce different event IDs."""
        id1 = compute_deterministic_event_id(
            seed=1, event_type="attack", payload={}, source="npc",
            parent_id=None, tick=1, seq=0,
        )
        id2 = compute_deterministic_event_id(
            seed=1, event_type="defend", payload={}, source="npc",
            parent_id=None, tick=1, seq=0,
        )
        self.assertNotEqual(id1, id2)

    def test_explicit_event_id_is_preserved(self):
        """Events with explicit event_id should NOT be overwritten during emit."""
        from app.rpg.core.clock import DeterministicClock
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=42))
        e = Event(type="test", payload={}, source="test", event_id="custom_id")
        bus.emit(e)
        self.assertEqual(e.event_id, "custom_id")


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

    def test_clock_now_advances_without_current_time(self):
        """now() should advance internal time."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        t1 = clock.now()
        t2 = clock.now()
        self.assertLess(t1, t2)


class TestEventWithDeterministicClock(unittest.TestCase):
    """PHASE 5.2 Fix #2: Events use DeterministicClock for timestamps."""

    def test_event_without_clock_has_none_timestamp(self):
        """Without a clock, timestamps should default to None until emit()."""
        e = Event(type="test", payload={}, source="test")
        self.assertIsNone(e.timestamp)

    def test_event_with_clock_uses_clock_time(self):
        """With a clock, timestamps come from DeterministicClock."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=0))

        e1 = Event(type="first", payload={}, source="test")
        e2 = Event(type="second", payload={}, source="test")

        bus.emit(e1)
        bus.emit(e2)

        self.assertEqual(e1.timestamp, 0.001)
        self.assertEqual(e2.timestamp, 0.002)

    def test_emit_uses_clock_for_new_events(self):
        """Events created during emit should use the clock."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=0))

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
        bus1 = EventBus(clock=clock1, determinism=DeterminismConfig(seed=0))
        events1 = []
        for i in range(3):
            e = Event(type=f"evt_{i}", payload={}, source="test")
            bus1.emit(e)
            events1.append(e)

        # Second run (simulating replay)
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        bus2 = EventBus(clock=clock2, determinism=DeterminismConfig(seed=0))
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

    def test_seen_set_grows_with_deque(self):
        """Set should stay in sync with the bounded deque."""
        bus = EventBus()
        # Use a small maxlen for testing
        maxlen = 10
        bus._seen_event_ids = __import__("collections").deque(maxlen=maxlen)

        for i in range(20):
            e = Event(type="test", payload={"i": i}, source="test")
            bus.emit(e)

        # Set size should be within maxlen + 1 (due to pruning timing)
        self.assertLessEqual(len(bus._seen_event_ids_set), maxlen + 1)

    def test_seen_set_removes_oldest_on_wrap(self):
        """When deque wraps, oldest entry should be removed from set."""
        bus = EventBus()
        maxlen = 3
        bus._seen_event_ids = __import__("collections").deque(maxlen=maxlen)

        # Emit 5 events
        for i in range(5):
            e = Event(type="test", payload={"i": i}, source="test")
            bus.emit(e)

        # After 5 events with maxlen=3:
        # The set should be bounded (within maxlen + 1 due to pruning timing)
        self.assertLessEqual(len(bus._seen_event_ids_set), maxlen + 1)


# ---------------------------------------------------------------------------
# Fix #4: First-Class Tick Tests
# ---------------------------------------------------------------------------

class TestFirstClassTick(unittest.TestCase):
    """PHASE 5.2 Fix #4: tick is a first-class field on Event."""

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
        bus = EventBus(determinism=DeterminismConfig(seed=0))
        bus.set_tick(42)

        e = Event(type="test", payload={}, source="test")
        bus.emit(e)

        self.assertEqual(e.tick, 42)

    def test_respects_explicit_tick_during_emit(self):
        """If event.tick is already set, emit() should respect it."""
        bus = EventBus(determinism=DeterminismConfig(seed=0))
        # Set bus tick to something different
        bus.set_tick(99)

        e = Event(type="test", payload={}, source="test", tick=42)
        bus.emit(e)

        # event.tick should remain 42 (explicit)
        self.assertEqual(e.tick, 42)

    def test_history_sorted_by_first_class_tick(self):
        """history() should sort by event.tick (first-class field)."""
        bus = EventBus(determinism=DeterminismConfig(seed=0))

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
    """rpg-design.txt BONUS: Replay should be bit-exact with seeded determinism."""

    def test_replay_is_bit_exact(self):
        """Running game twice with same setup should produce identical state."""
        seed = 123
        # First run
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        bus1 = EventBus(clock=clock1, determinism=DeterminismConfig(seed=seed))

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

        # Second run with identical setup (seeded determinism)
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        bus2 = EventBus(clock=clock2, determinism=DeterminismConfig(seed=seed))

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
        """Event IDs should be identical with same seed."""
        seed = 42

        # Run 1
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=seed))
        bus.set_tick(1)
        e1 = Event(type="a", payload={}, source="test")
        bus.emit(e1)
        bus.set_tick(2)
        e2 = Event(type="b", payload={}, source="test")
        bus.emit(e2)

        ids_run1 = [e1.event_id, e2.event_id]
        ticks_run1 = [e1.tick, e2.tick]
        timestamps_run1 = [e1.timestamp, e2.timestamp]

        # Run 2 (same seed)
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=seed))
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


# ---------------------------------------------------------------------------
# SeededRNG Tests
# ---------------------------------------------------------------------------

class TestSeededRNG(unittest.TestCase):
    """PHASE 5.2: SeededRNG provides deterministic randomness."""

    def test_rng_deterministic(self):
        """Two RNGs with same seed produce same sequence."""
        rng1 = SeededRNG(seed=42)
        rng2 = SeededRNG(seed=42)

        self.assertEqual(rng1.randint(0, 100), rng2.randint(0, 100))
        self.assertEqual(rng1.random(), rng2.random())
        self.assertEqual(rng1.choice([1, 2, 3]), rng2.choice([1, 2, 3]))

    def test_rng_different_seed_different_output(self):
        """Different seeds produce different output."""
        rng1 = SeededRNG(seed=1)
        rng2 = SeededRNG(seed=2)
        self.assertNotEqual(rng1.randint(0, 100000), rng2.randint(0, 100000))

    def test_rng_choice_empty_raises(self):
        """Choice from empty sequence raises IndexError."""
        rng = SeededRNG(seed=0)
        with self.assertRaises(IndexError):
            rng.choice([])

    def test_rng_seed_property(self):
        """Seed property returns original seed."""
        rng = SeededRNG(seed=99)
        self.assertEqual(rng.seed, 99)


# ---------------------------------------------------------------------------
# stable_json Tests
# ---------------------------------------------------------------------------

class TestStableJson(unittest.TestCase):
    """PHASE 5.2: stable_json provides deterministic serialization."""

    def test_dict_sorts_keys(self):
        """Dict keys should be sorted."""
        d = {"c": 3, "a": 1, "b": 2}
        result = stable_json(d)
        # Parse and verify order
        self.assertIn('"a":', result)
        idx_a = result.index('"a":')
        idx_b = result.index('"b":')
        idx_c = result.index('"c":')
        self.assertLess(idx_a, idx_b)
        self.assertLess(idx_b, idx_c)

    def test_nested_sorts_keys(self):
        """Nested dicts should also be sorted."""
        d = {"z": {"b": 2, "a": 1}, "a": 3}
        result = stable_json(d)
        idx_a = result.index('"a"')
        idx_z = result.index('"z"')
        self.assertLess(idx_a, idx_z)

    def test_rounds_floats(self):
        """Floats should be rounded to 6 decimal places."""
        result = stable_json({"x": 1.123456789})
        # Should be rounded
        self.assertIn("1.123457", result)

    def test_list_order_preserved(self):
        """Lists should maintain order."""
        result1 = stable_json([1, 2, 3])
        result2 = stable_json([1, 2, 3])
        self.assertEqual(result1, result2)

    def test_equivalent_input_same_output(self):
        """Same input produces identical output."""
        d = {"b": 2, "a": 1}
        self.assertEqual(stable_json(d), stable_json(d))


# ---------------------------------------------------------------------------
# Phase 52 — Deterministic Replay Hardening Tests (rpg-design.txt)
# ---------------------------------------------------------------------------

class TestPhase52DeterministicHardening(unittest.TestCase):
    """PHASE 5.2: Deterministic replay hardening tests from rpg-design.txt."""

    def test_emit_applies_context_tick_and_parent(self):
        """EventContext.tick and parent_id should both be applied during emit."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=1))
        event = Event(type="npc_action", payload={"x": 1}, source="npc")
        ctx = EventContext(parent_id="evt_parent", tick=7)

        bus.emit(event, context=ctx)

        emitted = bus.history()[0]
        self.assertEqual(emitted.parent_id, "evt_parent")
        self.assertEqual(emitted.tick, 7)
        self.assertEqual(emitted.payload["tick"], 7)

    def test_replay_mode_refuses_fresh_timestamp_generation(self):
        """Replay mode should raise RuntimeError when event.timestamp is missing."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=2))
        bus.set_replay_mode(True)

        event = Event(
            type="replayed_event",
            payload={"a": 1},
            source="sys",
            event_id="evt_known",
            timestamp=None,
        )

        try:
            bus.emit(event, replay=True)
            self.fail("Expected RuntimeError in replay mode when timestamp is missing")
        except RuntimeError as exc:
            self.assertIn("timestamp", str(exc))

    def test_replay_mode_refuses_fresh_event_id_generation(self):
        """Replay mode should raise RuntimeError when event.event_id is missing."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=3))
        bus.set_replay_mode(True)

        event = Event(
            type="replayed_event",
            payload={"a": 1},
            source="sys",
            event_id=None,
            timestamp=1.234,
        )

        try:
            bus.emit(event, replay=True)
            self.fail("Expected RuntimeError in replay mode when event_id is missing")
        except RuntimeError as exc:
            self.assertIn("event_id", str(exc))

    def test_load_history_clears_pending_queue(self):
        """load_history() should clear the pending event queue."""
        bus = EventBus(determinism=DeterminismConfig(seed=4))
        bus.emit(Event(type="one", payload={}, source="sys"))
        _ = bus.collect()

        bus.emit(Event(type="pending", payload={}, source="sys"))
        self.assertEqual(len(bus.collect()), 1)

        hist_bus = EventBus(determinism=DeterminismConfig(seed=4))
        hist_bus.emit(Event(type="saved", payload={}, source="sys"))
        history = hist_bus.history()

        bus.emit(Event(type="stale_pending", payload={}, source="sys"))
        bus.load_history(history)

        self.assertEqual(bus.collect(), [])
        self.assertEqual(len(bus.history()), 1)

    def test_context_tick_does_not_get_overwritten_by_current_tick(self):
        """EventContext.tick should not be overwritten by the bus's current tick."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=5))
        bus.set_tick(99)
        event = Event(type="ctx_tick", payload={}, source="sys")
        ctx = EventContext(parent_id=None, tick=4)

        bus.emit(event, context=ctx)

        emitted = bus.history()[0]
        self.assertEqual(emitted.tick, 4)
        self.assertEqual(emitted.payload["tick"], 4)

    def test_payload_mutation_after_emit_does_not_change_identity(self):
        """Nested payload mutation after emit must not affect assigned identity."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=77))
        event = Event(
            type="nested",
            payload={"outer": {"inner": 1}},
            source="sys",
        )

        bus.emit(event)
        original_id = event.event_id

        # Mutate original event payload after emit
        event.payload["outer"]["inner"] = 999

        self.assertEqual(event.event_id, original_id)
        self.assertEqual(bus.history()[0].event_id, original_id)
        self.assertEqual(bus.history()[0].payload["outer"]["inner"], 1)

    def test_cross_run_identity_stability(self):
        """Same seed + same events should produce identical event IDs across runs."""
        seed = 2026

        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        bus1 = EventBus(clock=clock1, determinism=DeterminismConfig(seed=seed))
        bus1.set_tick(1)
        e1a = Event(type="attack", payload={"target": "goblin"}, source="npc")
        e1b = Event(type="defend", payload={"target": "self"}, source="npc")
        bus1.emit(e1a)
        bus1.emit(e1b)
        ids1 = [e1a.event_id, e1b.event_id]

        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        bus2 = EventBus(clock=clock2, determinism=DeterminismConfig(seed=seed))
        bus2.set_tick(1)
        e2a = Event(type="attack", payload={"target": "goblin"}, source="npc")
        e2b = Event(type="defend", payload={"target": "self"}, source="npc")
        bus2.emit(e2a)
        bus2.emit(e2b)
        ids2 = [e2a.event_id, e2b.event_id]

        self.assertEqual(ids1, ids2)


if __name__ == "__main__":
    unittest.main()
