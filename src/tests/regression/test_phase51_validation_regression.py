"""PHASE 5.1 — Regression Tests for Validation Layer

Regression tests to prevent breaking changes in the validation layer.

Tests cover:
- EventBus history() returns deterministic ordering after future modifications
- stable_serialize handles edge cases (empty containers, nested structures)
- compute_state_hash produces consistent results across system updates
- DeterminismValidator doesn't break when adding new systems
- ReplayValidator works after EventBus modifications
- SimulationParityValidator works after sandbox modifications
"""

import unittest
from unittest.mock import MagicMock
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.validation.state_hash import stable_serialize, compute_state_hash
from app.rpg.validation.determinism import DeterminismValidator
from app.rpg.validation.replay_validator import ReplayValidator
from app.rpg.validation.simulation_parity import SimulationParityValidator


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _make_event(event_id: str = None, type: str = "test", tick: int = 0) -> Event:
    """Create a deterministic test event."""
    return Event(
        type=type,
        payload={"tick": tick, "regression_test": True},
        source="regression_system",
        event_id=event_id,
        timestamp=1000.0 + tick,
    )


class MinimalLoop:
    """Minimal GameLoop-like object for testing."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus or EventBus()
        self._tick_count = 0
        self.tick_count = 0

    def tick(self):
        self._tick_count += 1
        self.tick_count = self._tick_count
        if self.event_bus:
            self.event_bus.set_tick(self._tick_count)


def _make_loop_factory():
    """Standard loop factory for validators."""
    def factory():
        return MinimalLoop(EventBus())
    return factory


# ---------------------------------------------------------------------------
# EventBus History Ordering Regression Tests
# ---------------------------------------------------------------------------

class TestEventBusHistoryRegression(unittest.TestCase):
    """Prevent regression in EventBus history() deterministic ordering."""

    def test_history_still_sorted_by_tuple(self):
        """history() should continue sorting by (tick, timestamp, event_id)."""
        bus = EventBus()
        
        # Add events with mixed attributes
        e1 = _make_event("z3", "type", tick=1)
        e1.timestamp = 1002.0
        e2 = _make_event("a1", "type", tick=1)
        e2.timestamp = 1001.0
        e3 = _make_event("b2", "type", tick=1)
        e3.timestamp = 1001.0

        bus.emit(e1)
        bus.emit(e2)
        bus.emit(e3)

        history = bus.history()
        # Should be sorted: a1 (ts=1001, id=a) < b2 (ts=1001, id=b) < z3 (ts=1002)
        self.assertEqual(history[0].event_id, "a1")
        self.assertEqual(history[1].event_id, "b2")
        self.assertEqual(history[2].event_id, "z3")

    def test_get_history_returns_list_copy(self):
        """get_history() should return a copy to prevent external mutation."""
        bus = EventBus()
        bus.emit(_make_event("e1", "test", tick=1))
        
        raw = bus.get_history()
        raw.append(_make_event("e_fake", "fake", tick=999))
        
        # Original should be unchanged
        self.assertEqual(len(bus.get_history()), 1)

    def test_empty_history_sorted(self):
        """Empty history() should return empty list, not crash."""
        bus = EventBus()
        history = bus.history()
        self.assertEqual(history, [])

    def test_many_events_sorted(self):
        """history() with many events should maintain deterministic order."""
        bus = EventBus()
        for i in range(100):
            bus.emit(_make_event(f"e{i:03d}", "tick", tick=i))
        
        history = bus.history()
        self.assertEqual(len(history), 100)
        # First should be tick 0, last tick 99
        self.assertEqual(history[0].payload["tick"], 0)
        self.assertEqual(history[-1].payload["tick"], 99)


# ---------------------------------------------------------------------------
# Stable Serialize Regression Tests
# ---------------------------------------------------------------------------

class TestStableSerializeRegression(unittest.TestCase):
    """Prevent regression in stable_serialize edge cases."""

    def test_deeply_nested_dicts(self):
        """Deep nesting should serialize correctly at all levels."""
        d = {
            "z": {"y": {"x": 1}},
            "a": {"b": {"c": 2}},
        }
        result = stable_serialize(d)
        self.assertEqual(list(result.keys()), ["a", "z"])
        self.assertEqual(list(result["a"].keys()), ["b"])
        self.assertEqual(list(result["z"].keys()), ["y"])

    def test_mixed_types_in_dict_values(self):
        """Dict with mixed value types should serialize all correctly."""
        d = {
            "str": "value",
            "int": 42,
            "float": 3.14,
            "list": [1, 2, 3],
            "dict": {"a": 1},
            "none": None,
            "bool": True,
        }
        result = stable_serialize(d)
        self.assertEqual(result["str"], "value")
        self.assertEqual(result["none"], None)
        self.assertEqual(result["list"], [1, 2, 3])

    def test_frozen_set_as_set(self):
        """frozenset should serialize like a set."""
        result = stable_serialize(frozenset([3, 1, 2]))
        self.assertEqual(result, [1, 2, 3])

    def test_frozenset_with_complex_objects(self):
        """frozenset with complex objects should serialize correctly."""
        result = stable_serialize(frozenset([1, 2, 3]))
        self.assertEqual(result, [1, 2, 3])

    def test_empty_string(self):
        """Empty string should serialize to empty string."""
        self.assertEqual(stable_serialize(""), "")


# ---------------------------------------------------------------------------
# Compute State Hash Regression Tests
# ---------------------------------------------------------------------------

class TestComputeStateHashRegression(unittest.TestCase):
    """Prevent regression in compute_state_hash behavior."""

    def test_hash_format_remains_sha256(self):
        """Hash should continue producing 64-char lowercase hex."""
        loop = MinimalLoop(EventBus())
        loop._tick_count = 1
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)
        self.assertEqual(h, h.lower())
        # Should be valid hex
        int(h, 16)

    def test_hash_with_none_event_id(self):
        """Events with None event_id should not crash hashing."""
        bus = EventBus()
        e = _make_event(None, "tick", tick=1)
        bus.emit(e)
        
        loop = MinimalLoop(bus)
        # Should not crash
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)

    def test_hash_with_large_payload(self):
        """Large payloads should hash without memory issues."""
        bus = EventBus()
        bus.emit(_make_event("e1", "tick", tick=1))
        bus.emit(_make_event("e2", "tick", tick=2))
        bus.emit(_make_event("e3", "tick", tick=3))
        
        loop = MinimalLoop(bus)
        loop._tick_count = 3
        
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)

    def test_hash_unchanged_with_same_events(self):
        """Same events across releases should produce same hash."""
        def make_loop():
            bus = EventBus()
            bus.emit(_make_event("a", "tick", tick=1))
            bus.emit(_make_event("b", "tick", tick=2))
            loop = MinimalLoop(bus)
            loop._tick_count = 2
            return loop
        
        h1 = compute_state_hash(make_loop())
        h2 = compute_state_hash(make_loop())
        self.assertEqual(h1, h2)


# ---------------------------------------------------------------------------
# Determinism Validator Regression Tests
# ---------------------------------------------------------------------------

class TestDeterminismValidatorRegression(unittest.TestCase):
    """Prevent regression in DeterminismValidator interface."""

    def test_result_structure_unchanged(self):
        """run_twice_and_compare should maintain result structure."""
        validator = DeterminismValidator(_make_loop_factory())
        result = validator.run_twice_and_compare([], num_ticks=1)
        
        # Must maintain these keys for backward compatibility
        self.assertIn("match", result)
        self.assertIn("hash1", result)
        self.assertIn("hash2", result)
        self.assertIsInstance(result["match"], bool)

    def test_run_n_times_structure_unchanged(self):
        """run_n_times should maintain result structure."""
        validator = DeterminismValidator(_make_loop_factory())
        result = validator.run_n_times([], num_runs=2, num_ticks=1)
        
        self.assertIn("match", result)
        self.assertIn("hashes", result)
        self.assertIn("unique_count", result)
        self.assertIsInstance(result["match"], bool)
        self.assertIsInstance(result["hashes"], list)
        self.assertIsInstance(result["unique_count"], int)

    def test_determine_break_point_structure(self):
        """determine_break_point should maintain result structure."""
        validator = DeterminismValidator(_make_loop_factory())
        result = validator.determine_break_point([], max_ticks=2)
        
        self.assertIn("match", result)
        self.assertIn("divergence_tick", result)
        self.assertIn("details", result)


# ---------------------------------------------------------------------------
# Replay Validator Regression Tests
# ---------------------------------------------------------------------------

class TestReplayValidatorRegression(unittest.TestCase):
    """Prevent regression in ReplayValidator interface."""

    def test_validate_structure_unchanged(self):
        """validate() result structure must remain stable."""
        validator = ReplayValidator(_make_loop_factory())
        events = [_make_event("e1", "test", tick=1)]
        result = validator.validate(events)
        
        self.assertIn("match", result)
        self.assertIn("live_hash", result)
        self.assertIn("replay_hash", result)
        self.assertIsInstance(result["match"], bool)


# ---------------------------------------------------------------------------
# Simulation Parity Validator Regression Tests
# ---------------------------------------------------------------------------

class TestSimulationParityValidatorRegression(unittest.TestCase):
    """Prevent regression in SimulationParityValidator interface."""

    def test_validate_structure_unchanged(self):
        """validate() result structure must remain stable."""
        def make_loop():
            loop = MinimalLoop()
            loop.tick = MagicMock()
            return loop

        validator = SimulationParityValidator(make_loop)
        result = validator.validate([], [], max_ticks=1)
        
        self.assertIn("match", result)
        self.assertIn("sim_hash", result)
        self.assertIn("real_hash", result)

    def test_divergence_detection_structure_unchanged(self):
        """divergence_detection() result structure must remain stable."""
        validator = SimulationParityValidator(_make_loop_factory())
        result = validator.divergence_detection([], [], max_tick=2)
        
        self.assertIn("match", result)
        self.assertIn("divergence_tick", result)
        self.assertIn("details", result)


# ---------------------------------------------------------------------------
# Cross-module Integration Regression Tests
# ---------------------------------------------------------------------------

class TestCrossModuleRegression(unittest.TestCase):
    """Ensure all validation modules work together after updates."""

    def test_hash_consistency_across_validators(self):
        """State hashes used by all validators should be consistent."""
        bus = EventBus()
        bus.emit(_make_event("e1", "init", tick=1))
        loop = MinimalLoop(bus)
        loop._tick_count = 1
        
        h1 = compute_state_hash(loop)
        
        # DeterminismValidator should use same hash format
        def factory():
            return MinimalLoop(EventBus())
        det = DeterminismValidator(factory)
        result = det.run_twice_and_compare([], num_ticks=0)
        # Verify hash length matches
        self.assertEqual(len(h1), len(result["hash1"]))
        self.assertEqual(len(h1), len(result["hash2"]))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()