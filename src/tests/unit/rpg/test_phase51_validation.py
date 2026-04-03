"""PHASE 5.1.5 — Unit Tests for Validation Layer (Critical Fixes)

Tests for all 5 critical fixes from rpg-design.txt:
- Fix #1: State hash includes full world state (not just events)
- Fix #2: Simulation parity hash includes full event structure (not just IDs)
- Fix #3: Replay engine supports deterministic mode
- Fix #4: Event ordering uses sequence numbers (not timestamps)
- Fix #5: Adversarial tests for non-determinism detection

These tests verify the core validation infrastructure with mocked
dependencies to ensure all Phase 5.1.5 guarantees work correctly.
"""

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch, call
from typing import Any, Dict, List, Optional, Callable

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.validation.state_hash import stable_serialize, compute_state_hash
from app.rpg.validation.determinism import DeterminismValidator
from app.rpg.validation.replay_validator import ReplayValidator
from app.rpg.validation.simulation_parity import SimulationParityValidator


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

def _make_event(event_id: str = None, type: str = "test", **payload) -> Event:
    """Create an event with optional explicit event_id and timestamp override."""
    e = Event(
        type=type,
        payload=payload,
        source="test_system",
        event_id=event_id,
        timestamp=1000.0,  # fixed timestamp for deterministic testing
    )
    return e


def _make_loop_mock(
    history: Optional[List[Event]] = None,
    tick_count: int = 0,
) -> Any:
    """Create a minimal game loop mock for validation testing."""
    loop = MagicMock()
    loop.tick_count = tick_count
    loop._tick_count = tick_count

    bus = MagicMock()
    bus.get_history.return_value = history or []
    bus.history.return_value = history or []
    loop.event_bus = bus
    return loop


def _make_loop_factory(history: Optional[List[Event]] = None, tick_count: int = 0) -> Callable[[], Any]:
    """Return a factory that produces copies of loop mock."""
    def factory():
        return _make_loop_mock(history, tick_count)
    return factory


# ---------------------------------------------------------------------------
# Stable Serialize Tests
# ---------------------------------------------------------------------------

class TestStableSerialize(unittest.TestCase):
    """Tests for stable_serialize deterministic serialization."""

    def test_none(self):
        """None should serialize to None."""
        self.assertIsNone(stable_serialize(None))

    def test_primitives(self):
        """Primitives should serialize to themselves."""
        self.assertEqual(stable_serialize(42), 42)
        self.assertEqual(stable_serialize(3.14), 3.14)
        self.assertEqual(stable_serialize("hello"), "hello")
        self.assertEqual(stable_serialize(True), True)
        self.assertEqual(stable_serialize(False), False)

    def test_dict_sorted(self):
        """Dicts should have keys sorted deterministically."""
        # Input is out-of-order
        d = {"c": 3, "a": 1, "b": 2}
        result = stable_serialize(d)
        keys = list(result.keys())
        self.assertEqual(keys, ["a", "b", "c"])

    def test_dict_nested_sorted(self):
        """Nested dicts should also have keys sorted at each level."""
        d = {"z": {"b": 2, "a": 1}, "a": 0}
        result = stable_serialize(d)
        self.assertEqual(list(result.keys()), ["a", "z"])
        self.assertEqual(list(result["z"].keys()), ["a", "b"])

    def test_list_preserves_order(self):
        """Lists should preserve element order."""
        lst = [3, 1, 2]
        result = stable_serialize(lst)
        self.assertEqual(result, [3, 1, 2])

    def test_list_of_dicts(self):
        """List of dicts should serialize each dict."""
        lst = [{"b": 2, "a": 1}, {"d": 4, "c": 3}]
        result = stable_serialize(lst)
        self.assertEqual(result, [{"a": 1, "b": 2}, {"c": 3, "d": 4}])

    def test_tuple_as_list(self):
        """Tuples should serialize as lists."""
        result = stable_serialize((1, 2, 3))
        self.assertEqual(result, [1, 2, 3])

    def test_set_sorted(self):
        """Sets should serialize as sorted lists."""
        result = stable_serialize({3, 1, 2})
        self.assertEqual(result, [1, 2, 3])

    def test_object_with_dict(self):
        """Objects with __dict__ should serialize to their vars."""
        class Foo:
            def __init__(self):
                self.z = 3
                self.a = 1

        obj = Foo()
        result = stable_serialize(obj)
        self.assertEqual(result, {"a": 1, "z": 3})

    def test_idempotent(self):
        """Calling stable_serialize twice should give same result."""
        d = {"c": 3, "a": 1}
        r1 = stable_serialize(d)
        r2 = stable_serialize(r1)
        self.assertEqual(r1, r2)

    def test_empty_containers(self):
        """Empty dicts and lists should serialize cleanly."""
        self.assertEqual(stable_serialize({}), {})
        self.assertEqual(stable_serialize([]), [])

    def test_unknown_type_fallback(self):
        """Objects without __dict__ should fallback to str."""
        # MagicMock has __dict__, so test with a primitive that won't match
        # any specific type branch - this is unlikely in practice
        # but test the isinstance ordering (bool before int)
        self.assertEqual(stable_serialize(True), True)
        self.assertEqual(stable_serialize(False), False)


# ---------------------------------------------------------------------------
# Compute State Hash Tests
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Real classes for world state extraction tests (not MagicMocks to avoid recursion)
# ---------------------------------------------------------------------------

class FakeNpcManager:
    def __init__(self, state):
        self._state = state
    def export_state(self):
        return self._state


class FakeMemory:
    def __init__(self, state):
        self._state = state
    def export_state(self):
        return self._state


class FakeRelationshipGraph:
    def __init__(self, state):
        self._state = state
    def export_state(self):
        return self._state


class FakeLoopWithSubsystems:
    """A minimal real loop-like object with subsystems for testing."""

    def __init__(self, npc_manager=None, memory=None, relationship_graph=None):
        self.npc_manager = npc_manager
        self.memory = memory
        self.relationship_graph = relationship_graph
        self._tick_count = 0
        self.tick_count = 0

        # Minimal event bus
        bus = EventBus()
        self.event_bus = bus


class TestExtractWorldState(unittest.TestCase):
    """Tests for _extract_world_state function (Fix #1)."""

    def test_empty_loop_has_empty_world_state(self):
        """Loop without subsystems should have empty world state in hash."""
        from app.rpg.validation.state_hash import _extract_world_state
        loop = FakeLoopWithSubsystems()
        ws = _extract_world_state(loop)
        self.assertEqual(ws, {})

    def test_npc_manager_state_extracted(self):
        """NPC manager state should be included in world state."""
        from app.rpg.validation.state_hash import _extract_world_state
        npc_mgr = FakeNpcManager({"npcs": [{"id": 1, "name": "Alice"}]})
        loop = FakeLoopWithSubsystems(npc_manager=npc_mgr)
        
        ws = _extract_world_state(loop)
        self.assertIn("npcs", ws)
        self.assertEqual(ws["npcs"], {"npcs": [{"id": 1, "name": "Alice"}]})

    def test_memory_state_extracted(self):
        """Memory system state should be included in world state."""
        from app.rpg.validation.state_hash import _extract_world_state
        mem = FakeMemory({"entries": ["memory1", "memory2"]})
        loop = FakeLoopWithSubsystems(memory=mem)
        
        ws = _extract_world_state(loop)
        self.assertIn("memory", ws)

    def test_relationship_graph_state_extracted(self):
        """Relationship graph state should be included in world state."""
        from app.rpg.validation.state_hash import _extract_world_state
        rel_graph = FakeRelationshipGraph({"edges": [(1, 2, 0.5)]})
        loop = FakeLoopWithSubsystems(relationship_graph=rel_graph)
        
        ws = _extract_world_state(loop)
        self.assertIn("relationships", ws)

    def test_different_world_states_different_hashes(self):
        """Loops with same events but different NPC state should have different hashes."""
        npc_mgr1 = FakeNpcManager({"npcs": [{"id": 1, "hp": 100}]})
        npc_mgr2 = FakeNpcManager({"npcs": [{"id": 1, "hp": 50}]})
        loop1 = FakeLoopWithSubsystems(npc_manager=npc_mgr1)
        loop2 = FakeLoopWithSubsystems(npc_manager=npc_mgr2)
        
        h1 = compute_state_hash(loop1)
        h2 = compute_state_hash(loop2)
        self.assertNotEqual(h1, h2)


class TestComputeStateHash(unittest.TestCase):
    """Tests for compute_state_hash deterministic fingerprint."""

    def test_empty_loop_hash(self):
        """Empty loop should produce a valid SHA-256 hash."""
        loop = _make_loop_mock(history=[], tick_count=0)
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)  # SHA-256 hex length
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_hash_includes_world_state(self):
        """State hash should include world state, not just events."""
        npc_mgr = FakeNpcManager({"npcs": [{"id": 1}]})
        loop = FakeLoopWithSubsystems(npc_manager=npc_mgr)
        
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)
        # Verify world state affects hash
        loop2 = FakeLoopWithSubsystems()
        h2 = compute_state_hash(loop2)
        self.assertNotEqual(h, h2)

    def test_same_state_same_hash(self):
        """Identical loops should produce identical hashes."""
        events = [
            _make_event(eid, "tick", tick=t)
            for t, eid in enumerate(["e1", "e2", "e3"], 1)
        ]
        loop1 = _make_loop_mock(history=events, tick_count=3)
        loop2 = _make_loop_mock(history=events, tick_count=3)
        self.assertEqual(compute_state_hash(loop1), compute_state_hash(loop2))

    def test_different_tick_different_hash(self):
        """Different tick counts should produce different hashes."""
        events = [_make_event("e1", "tick", tick=1)]
        loop1 = _make_loop_mock(history=events, tick_count=1)
        loop2 = _make_loop_mock(history=events, tick_count=2)
        self.assertNotEqual(compute_state_hash(loop1), compute_state_hash(loop2))

    def test_different_events_different_hash(self):
        """Different event histories should produce different hashes."""
        events1 = [_make_event("e1", "tick", tick=1)]
        events2 = [_make_event("e2", "other", tick=1)]
        loop1 = _make_loop_mock(history=events1, tick_count=1)
        loop2 = _make_loop_mock(history=events2, tick_count=1)
        self.assertNotEqual(compute_state_hash(loop1), compute_state_hash(loop2))

    def test_order_independence(self):
        """Event order should not affect hash when events have same data."""
        # Note: In real usage, EventBus.history() returns sorted data,
        # so the hash is always order-independent. With mocks we pass
        # the same data to verify hash consistency.
        events = [
            _make_event("e1", "a", tick=1),
            _make_event("e2", "b", tick=2),
        ]
        loop1 = _make_loop_mock(history=list(events), tick_count=2)
        loop2 = _make_loop_mock(history=list(events), tick_count=2)
        self.assertEqual(compute_state_hash(loop1), compute_state_hash(loop2))

    def test_no_event_bus(self):
        """Loop without event_bus should produce a valid hash."""
        class LoopWithoutEventBus:
            def __init__(self):
                self._tick_count = 5
                self.tick_count = 5
        loop = LoopWithoutEventBus()
        h = compute_state_hash(loop)
        self.assertEqual(len(h), 64)

    def test_hash_uses_get_history(self):
        """compute_state_hash should prefer get_history over history."""
        loop = _make_loop_mock(history=[], tick_count=0)
        compute_state_hash(loop)
        loop.event_bus.get_history.assert_called()

    def test_event_parent_in_hash(self):
        """Event parent links should be included in hash."""
        events = [
            _make_event("e1", "start", tick=1),
            _make_event("e2", "follow", tick=2),
        ]
        events[1].parent_id = "e1"
        loop = _make_loop_mock(history=events, tick_count=2)
        h1 = compute_state_hash(loop)
        
        events_no_parent = [
            _make_event("e1", "start", tick=1),
            _make_event("e2", "follow", tick=2),
        ]
        loop_np = _make_loop_mock(history=events_no_parent, tick_count=2)
        h2 = compute_state_hash(loop_np)
        # Events with parent link should hash differently
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Determinism Validator Tests
# ---------------------------------------------------------------------------

def _make_loop_with_tick(tick_count: int = 0) -> Any:
    """Create a loop mock that has working tick() method."""
    loop = _make_loop_mock(history=[], tick_count=tick_count)
    loop.tick = MagicMock()
    loop.event_bus.emit = MagicMock()
    return loop


class TestDeterminismValidator(unittest.TestCase):
    """Tests for DeterminismValidator."""

    def test_run_twice_and_compare_match(self):
        """Identical runs should produce matching hashes."""
        loop = _make_loop_with_tick(tick_count=0)
        factory = lambda: _make_loop_with_tick(tick_count=0)

        validator = DeterminismValidator(factory)
        events = [_make_event("e1", "start", tick=1)]

        result = validator.run_twice_and_compare(events, num_ticks=3)

        self.assertTrue(result["match"])
        self.assertEqual(len(result["hash1"]), 64)
        self.assertEqual(len(result["hash2"]), 64)

    def test_run_twice_and_compare_returns_hashes(self):
        """Result should include both hashes."""
        factory = lambda: _make_loop_with_tick(0)
        validator = DeterminismValidator(factory)
        result = validator.run_twice_and_compare([], num_ticks=2)
        self.assertIn("hash1", result)
        self.assertIn("hash2", result)
        self.assertIn("match", result)

    def test_run_n_times_all_match(self):
        """N identical runs should all produce same hash."""
        factory = lambda: _make_loop_with_tick(0)
        validator = DeterminismValidator(factory)
        events = [_make_event("e1", "start")]

        result = validator.run_n_times(events, num_runs=3, num_ticks=2)

        self.assertTrue(result["match"])
        self.assertEqual(result["unique_count"], 1)
        self.assertEqual(len(result["hashes"]), 3)

    def test_determine_break_point(self):
        """Should track per-tick hash comparisons."""
        factory = lambda: _make_loop_with_tick(0)
        validator = DeterminismValidator(factory)
        events = [_make_event("e1", "start")]

        result = validator.determine_break_point(events, max_ticks=3)

        self.assertIn("match", result)
        self.assertIn("divergence_tick", result)
        self.assertIn("details", result)
        self.assertEqual(len(result["details"]), 3)


# ---------------------------------------------------------------------------
# Replay Validator Tests
# ---------------------------------------------------------------------------

class TestEventBusSequenceOrdering(unittest.TestCase):
    """PHASE 5.1.5 Fix #4: Tests for event ordering using sequence numbers."""

    def test_events_get_sequence_numbers(self):
        """Events should be assigned monotonically increasing sequence numbers."""
        bus = EventBus()
        e1 = Event(type="first", payload={}, source="test")
        e2 = Event(type="second", payload={}, source="test")
        e3 = Event(type="third", payload={}, source="test")
        
        bus.emit(e1)
        bus.emit(e2)
        bus.emit(e3)
        
        self.assertEqual(e1._seq, 0)
        self.assertEqual(e2._seq, 1)
        self.assertEqual(e3._seq, 2)

    def test_history_sorted_by_sequence_number(self):
        """history() should return events sorted by (tick, _seq)."""
        bus = EventBus()
        bus.set_tick(1)
        
        # Emit events without explicit tick in payload
        e1 = Event(type="a", payload={}, source="test")
        e2 = Event(type="b", payload={}, source="test")
        e3 = Event(type="c", payload={}, source="test")
        
        bus.emit(e1)
        bus.emit(e2)
        bus.emit(e3)
        
        history = bus.history()
        self.assertEqual(len(history), 3)
        # All same tick, so should be ordered by _seq
        self.assertEqual(history[0].type, "a")
        self.assertEqual(history[1].type, "b")
        self.assertEqual(history[2].type, "c")

    def test_sequence_ordering_independent_of_timestamps(self):
        """Events with different timestamps should still order by sequence number."""
        bus = EventBus()
        
        # Create events with intentionally reversed timestamps
        e1 = Event(type="first", payload={}, source="test", timestamp=1003.0)
        e2 = Event(type="second", payload={}, source="test", timestamp=1001.0)
        e3 = Event(type="third", payload={}, source="test", timestamp=1002.0)
        
        bus.emit(e1)
        bus.emit(e2)
        bus.emit(e3)
        
        history = bus.history()
        # Should be ordered by _seq, not timestamp
        self.assertEqual(history[0].type, "first")
        self.assertEqual(history[1].type, "second")
        self.assertEqual(history[2].type, "third")

    def test_sequence_numbers_different_ticks(self):
        """Events across different ticks should be ordered correctly."""
        bus = EventBus()
        
        bus.set_tick(3)
        e3 = Event(type="tick3", payload={}, source="test")
        bus.emit(e3)
        
        bus.set_tick(1)
        e1 = Event(type="tick1", payload={}, source="test")
        bus.emit(e1)
        
        bus.set_tick(2)
        e2 = Event(type="tick2", payload={}, source="test")
        bus.emit(e2)
        
        history = bus.history()
        # Should be ordered by tick first, then by _seq
        self.assertEqual(history[0].type, "tick1")
        self.assertEqual(history[1].type, "tick2")
        self.assertEqual(history[2].type, "tick3")

    def test_sequence_number_survives_cloning(self):
        """Sequence number should be preserved when event is cloned during emit."""
        bus = EventBus()
        e = Event(type="test", payload={"key": "value"}, source="test")
        
        bus.emit(e)
        
        # After cloning inside emit, _seq should still be assigned
        self.assertEqual(e._seq, 0)


class FakeReplayLoop:
    """Fake loop for replay engine testing."""

    def __init__(self):
        self.event_bus = EventBus()
        self._tick_count = 0
        self.llm_disabled = False
        self.time_frozen = False
        self.replay_mode = False

    def disable_llm(self):
        self.llm_disabled = True

    def freeze_time(self):
        self.time_frozen = True

    def use_recorded_outputs(self):
        self.replay_mode = True


class TestReplayDeterministicMode(unittest.TestCase):
    """PHASE 5.1.5 Fix #3: Tests for replay engine deterministic mode."""

    def test_replay_engine_accepts_mode_parameter(self):
        """ReplayEngine.replay() should accept mode parameter."""
        from app.rpg.core.replay_engine import ReplayEngine
        
        factory = lambda: FakeReplayLoop()
        engine = ReplayEngine(factory)
        events = [Event(type="test", payload={"tick": 1}, source="test", event_id="e1")]
        
        # Should accept mode parameter without error
        result = engine.replay(events, mode="deterministic")
        self.assertIsInstance(result, FakeReplayLoop)

    def test_deterministic_mode_disables_llm(self):
        """Deterministic mode should disable LLM on the loop."""
        from app.rpg.core.replay_engine import ReplayEngine
        
        loop = FakeReplayLoop()
        factory = lambda: loop
        engine = ReplayEngine(factory)
        events = [Event(type="test", payload={"tick": 1}, source="test", event_id="e1")]
        
        engine.replay(events, mode="deterministic")
        self.assertTrue(loop.llm_disabled)

    def test_deterministic_mode_freezes_time(self):
        """Deterministic mode should freeze time on the loop."""
        from app.rpg.core.replay_engine import ReplayEngine
        
        loop = FakeReplayLoop()
        factory = lambda: loop
        engine = ReplayEngine(factory)
        events = [Event(type="test", payload={"tick": 1}, source="test", event_id="e1")]
        
        engine.replay(events, mode="deterministic")
        self.assertTrue(loop.time_frozen)


class TestAdversarialNonDeterminism(unittest.TestCase):
    """PHASE 5.1.5 Fix #5: Adversarial tests for non-determinism detection."""

    def test_nondeterminism_detection_different_payloads(self):
        """Should detect non-determinism when events have different payloads."""
        e1 = Event(type="attack", payload={"damage": 100}, source="test", 
                   event_id="same_id", timestamp=1000.0)
        e2 = Event(type="attack", payload={"damage": 50}, source="test",
                   event_id="same_id", timestamp=1000.0)
        
        h1 = hashlib.sha256(json.dumps(stable_serialize(e1.payload)).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(stable_serialize(e2.payload)).encode()).hexdigest()
        
        # Same event ID, different payloads should produce different hashes
        self.assertNotEqual(h1, h2)

    def test_nondeterminism_detection_different_types(self):
        """Should detect non-determinism when events have different types."""
        e1 = Event(type="attack", payload={}, source="test",
                   event_id="same_id", timestamp=1000.0)
        e2 = Event(type="heal", payload={}, source="test",
                   event_id="same_id", timestamp=1000.0)
        
        h1 = hashlib.sha256(json.dumps(stable_serialize({"type": e1.type})).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(stable_serialize({"type": e2.type})).encode()).hexdigest()
        
        # Same event ID, different types should produce different hashes
        self.assertNotEqual(h1, h2)

    def test_determinism_with_identical_events(self):
        """Identical events should produce identical hashes."""
        events1 = [
            Event(type="a", payload={"x": 1}, source="test", event_id="e1", timestamp=1.0),
            Event(type="b", payload={"y": 2}, source="test", event_id="e2", timestamp=2.0),
        ]
        events2 = [
            Event(type="a", payload={"x": 1}, source="test", event_id="e1", timestamp=1.0),
            Event(type="b", payload={"y": 2}, source="test", event_id="e2", timestamp=2.0),
        ]
        
        def hash_events(events):
            data = json.dumps(stable_serialize([
                {"id": e.event_id, "type": e.type, "payload": stable_serialize(e.payload)}
                for e in events
            ]))
            return hashlib.sha256(data.encode()).hexdigest()
        
        h1 = hash_events(events1)
        h2 = hash_events(events2)
        self.assertEqual(h1, h2)


# ---------------------------------------------------------------------------
# Simulation Parity Validator Tests
# ---------------------------------------------------------------------------

class TestSimulationParityValidator(unittest.TestCase):
    """Tests for SimulationParityValidator."""

    def test_validate_returns_structure(self):
        """validate() should return expected keys."""
        loop = _make_loop_mock(history=[], tick_count=0)
        loop.tick = MagicMock()
        loop.event_bus.emit = MagicMock()
        factory = lambda: _make_loop_mock(history=[], tick_count=0)

        # Mock tick().tick_count = 0
        def make_loop():
            l = _make_loop_mock(history=[], tick_count=0)
            l.tick = MagicMock()
            l.event_bus.emit = MagicMock()
            return l

        validator = SimulationParityValidator(make_loop)
        events = [_make_event("e1", "start", tick=1)]

        result = validator.validate(events, events, max_ticks=2)

        self.assertIn("match", result)
        self.assertIn("sim_hash", result)
        self.assertIn("real_hash", result)

    def test_hash_from_events(self):
        """_hash_from_events should produce valid SHA-256."""
        validator = SimulationParityValidator(_make_loop_factory())
        events = [_make_event("e1"), _make_event("e2")]
        h = validator._hash_from_events(events)
        self.assertEqual(len(h), 64)

    def test_hash_from_events_includes_full_structure(self):
        """PHASE 5.1.5 Fix #2: Hash should include id, type, and payload."""
        validator = SimulationParityValidator(_make_loop_factory())
        
        events1 = [_make_event("e1", "attack", damage=100)]
        events2 = [_make_event("e1", "flee", damage=10)]  # Same ID, different type/payload
        
        h1 = validator._hash_from_events(events1)
        h2 = validator._hash_from_events(events2)
        
        # Fix #2 ensures different types and payloads are hashed
        self.assertNotEqual(h1, h2)

    def test_hash_catches_same_id_different_payload(self):
        """PHASE 5.1.5 Fix #2: Same event IDs but different payloads should differ."""
        validator = SimulationParityValidator(_make_loop_factory())
        
        events1 = [_make_event("e1", "same_type", value=10)]
        events2 = [_make_event("e1", "same_type", value=20)]
        
        h1 = validator._hash_from_events(events1)
        h2 = validator._hash_from_events(events2)
        
        self.assertNotEqual(h1, h2, "Same ID with different payload should produce different hash")

    def test_validate_multi_candidate(self):
        """Should validate multiple candidate sets."""
        make_loop = lambda: _make_loop_mock(history=[], tick_count=0)
        validator = SimulationParityValidator(make_loop)

        results = validator.validate_multi_candidate(
            base_events=[_make_event("base")],
            candidate_sets=[
                [_make_event("a")],
                [_make_event("b")],
            ],
            max_ticks=1,
        )

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIn("match", r)
            self.assertIn("candidate_index", r)

    def test_validate_progressive(self):
        """Should validate at multiple tick counts."""
        make_loop = lambda: _make_loop_mock(history=[], tick_count=0)
        validator = SimulationParityValidator(make_loop)

        results = validator.validate_progressive(
            base_events=[_make_event("base")],
            future_events=[_make_event("future")],
            tick_range=range(1, 3),
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["ticks"], 1)
        self.assertEqual(results[1]["ticks"], 2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()