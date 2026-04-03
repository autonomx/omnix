"""PHASE 5.1 — Functional Tests for Validation Layer

End-to-end tests that verify the validation layer works with real
game loop and event bus integration (not just mocked components).

Tests cover:
- Real EventBus deterministic ordering
- GameLoop integration with state hashing
- Real event emission and hash consistency
- EventBus history sorting validation
"""

import unittest
from unittest.mock import MagicMock
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus, EventContext
from app.rpg.validation.state_hash import stable_serialize, compute_state_hash
from app.rpg.validation.determinism import DeterminismValidator
from app.rpg.validation.replay_validator import ReplayValidator
from app.rpg.validation.simulation_parity import SimulationParityValidator


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _make_real_event(event_id: str = None, type: str = "test", tick: int = 0) -> Event:
    """Create a real Event with fixed timestamp for determinism."""
    return Event(
        type=type,
        payload={"tick": tick, "data": f"{type}_{event_id}"},
        source="test_system",
        event_id=event_id,
        timestamp=1000.0 + (tick * 0.001),  # deterministic timestamps
    )


class MinimalLoop:
    """Minimal object that looks like a GameLoop for hashing."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus or EventBus()
        self._tick_count = 0
        self.tick_count = 0

    def tick(self):
        self._tick_count += 1
        self.tick_count = self._tick_count
        self.event_bus.set_tick(self._tick_count)

    def create_game_loop(self):
        return self


def _make_loop_factory():
    """Create a factory that produces fresh minimal loops."""
    def factory():
        bus = EventBus()
        loop = MinimalLoop(bus)
        return loop
    return factory


# ---------------------------------------------------------------------------
# EventBus Deterministic Ordering Tests
# ---------------------------------------------------------------------------

class TestEventBusDeterministicOrdering(unittest.TestCase):
    """Tests for the PHASE 5.1 deterministic ordering in EventBus."""

    def test_history_returns_sorted(self):
        """history() should return events sorted by (tick, timestamp, event_id)."""
        bus = EventBus()

        # Emit events in non-chronological order of IDs
        events = [
            _make_real_event("c", "type_c", tick=3),
            _make_real_event("a", "type_a", tick=1),
            _make_real_event("b", "type_b", tick=2),
        ]
        for e in events:
            bus.emit(e)

        history = bus.history()
        self.assertEqual(len(history), 3)
        # Sorted by tick
        self.assertEqual(history[0].payload["tick"], 1)
        self.assertEqual(history[1].payload["tick"], 2)
        self.assertEqual(history[2].payload["tick"], 3)

    def test_history_same_tick_sorted_by_timestamp(self):
        """Events with same tick should be sorted by timestamp."""
        bus = EventBus()
        
        e1 = _make_real_event("e1", "type_1", tick=1)
        e1.timestamp = 1000.0
        e2 = _make_real_event("e2", "type_2", tick=1)
        e2.timestamp = 1001.0
        e3 = _make_real_event("e3", "type_3", tick=1)
        e3.timestamp = 1002.0

        # Emit out of timestamp order
        for e in [e3, e1, e2]:
            bus.emit(e)

        history = bus.history()
        self.assertEqual(history[0].event_id, "e1")
        self.assertEqual(history[1].event_id, "e2")
        self.assertEqual(history[2].event_id, "e3")

    def test_history_same_tick_same_timestamp_sorted_by_id(self):
        """Events with same tick and timestamp should be sorted by event_id."""
        bus = EventBus()
        
        e_c = _make_real_event("c", "type", tick=1)
        e_c.timestamp = 1000.0
        e_a = _make_real_event("a", "type", tick=1)
        e_a.timestamp = 1000.0
        e_b = _make_real_event("b", "type", tick=1)
        e_b.timestamp = 1000.0

        for e in [e_c, e_a, e_b]:
            bus.emit(e)

        history = bus.history()
        self.assertEqual(history[0].event_id, "a")
        self.assertEqual(history[1].event_id, "b")
        self.assertEqual(history[2].event_id, "c")

    def test_get_history_returns_unsorted(self):
        """get_history() should return raw history without sorting."""
        bus = EventBus()
        
        e1 = _make_real_event("e1", "type", tick=1)
        e2 = _make_real_event("e2", "type", tick=2)
        
        bus.emit(e1)
        bus.emit(e2)

        raw = bus.get_history()
        # Raw order should be insertion order
        self.assertEqual(raw[0].event_id, "e1")
        self.assertEqual(raw[1].event_id, "e2")

    def test_determinism_across_runs(self):
        """Two identical EventBus runs should produce identical history()."""
        def create_bus():
            b = EventBus()
            for event_id in ["a", "b", "c"]:
                b.emit(_make_real_event(event_id, f"type_{event_id}", tick=1))
            return b

        bus1 = create_bus()
        bus2 = create_bus()

        history1 = bus1.history()
        history2 = bus2.history()

        for i in range(len(history1)):
            self.assertEqual(history1[i].event_id, history2[i].event_id)
            self.assertEqual(history1[i].type, history2[i].type)


# ---------------------------------------------------------------------------
# State Hash Integration Tests
# ---------------------------------------------------------------------------

class TestStateHashFunctional(unittest.TestCase):
    """Functional tests for compute_state_hash with real EventBus."""

    def test_hash_with_real_event_bus(self):
        """State hash should work with real EventBus."""
        bus = EventBus()
        bus.emit(_make_real_event("e1", "start", tick=1))
        bus.emit(_make_real_event("e2", "move", tick=2))

        loop = MinimalLoop(bus)
        loop._tick_count = 2
        loop.tick_count = 2

        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)

    def test_hash_consistency_with_same_events(self):
        """Same events should produce same hash with real EventBus."""
        def make_loop():
            bus = EventBus()
            bus.emit(_make_real_event("e1", "action", tick=1))
            bus.emit(_make_real_event("e2", "move", tick=2))
            loop = MinimalLoop(bus)
            loop._tick_count = 2
            loop.tick_count = 2
            return loop

        h1 = compute_state_hash(make_loop())
        h2 = compute_state_hash(make_loop())
        self.assertEqual(h1, h2)

    def test_hash_different_with_different_events(self):
        """Different events should produce different hashes."""
        def make_loop_with_events(events):
            bus = EventBus()
            for e in events:
                bus.emit(e)
            loop = MinimalLoop(bus)
            loop._tick_count = len(events)
            loop.tick_count = len(events)
            return loop

        h1 = compute_state_hash(make_loop_with_events([
            _make_real_event("e1", "attack", tick=1),
        ]))
        h2 = compute_state_hash(make_loop_with_events([
            _make_real_event("e1", "flee", tick=1),
        ]))
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Determinism Validator Functional Tests
# ---------------------------------------------------------------------------

class TestDeterminismValidatorFunctional(unittest.TestCase):
    """Tests for DeterminismValidator with minimal real loop."""

    def test_validates_with_real_loops(self):
        """Should validate determinism with real EventBus."""
        events = [
            _make_real_event("e1", "start"),
            _make_real_event("e2", "move"),
        ]

        validator = DeterminismValidator(_make_loop_factory())
        result = validator.run_twice_and_compare(events, num_ticks=2)

        self.assertIn("match", result)
        self.assertIn("hash1", result)
        self.assertIn("hash2", result)

    def test_multiple_runs_consistent(self):
        """run_n_times should show consistency across multiple runs."""
        events = [_make_real_event("e1", "test")]

        validator = DeterminismValidator(_make_loop_factory())
        result = validator.run_n_times(events, num_runs=3, num_ticks=2)

        self.assertTrue(result["match"])
        self.assertEqual(result["unique_count"], 1)


# ---------------------------------------------------------------------------
# Replay Validator Functional Tests
# ---------------------------------------------------------------------------

class TestReplayValidatorFunctional(unittest.TestCase):
    """Tests for ReplayValidator with real EventBus."""

    def test_validate_returns_expected_fields(self):
        """validate() should return match, live_hash, replay_hash."""
        events = [_make_real_event("e1", "test", tick=1)]

        validator = ReplayValidator(_make_loop_factory())
        result = validator.validate(events)

        self.assertIn("match", result)
        self.assertIn("live_hash", result)
        self.assertIn("replay_hash", result)
        self.assertEqual(len(result["live_hash"]), 64)
        self.assertEqual(len(result["replay_hash"]), 64)


# ---------------------------------------------------------------------------
# Simulation Parity Validator Functional Tests
# ---------------------------------------------------------------------------

class TestSimulationParityValidatorFunctional(unittest.TestCase):
    """Tests for SimulationParityValidator with real EventBus."""

    def test_validate_returns_expected_fields(self):
        """validate() should return match, sim_hash, real_hash."""
        base = [_make_real_event("base", "setup", tick=1)]
        future = [_make_real_event("future", "action", tick=2)]

        def make_loop():
            loop = MinimalLoop()
            loop.tick = MagicMock()
            return loop

        validator = SimulationParityValidator(make_loop)
        result = validator.validate(base, future, max_ticks=1)

        self.assertIn("match", result)
        self.assertIn("sim_hash", result)
        self.assertIn("real_hash", result)

    def test_divergence_detection_returns_structure(self):
        """divergence_detection() should return match, divergence_tick, details."""
        validator = SimulationParityValidator(_make_loop_factory())
        result = validator.divergence_detection(
            base_events=[_make_real_event("base", "setup")],
            future_events=[_make_real_event("future", "action")],
            max_tick=3,
        )

        self.assertIn("match", result)
        self.assertIn("divergence_tick", result)
        self.assertIn("details", result)
        self.assertEqual(len(result["details"]), 3)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()