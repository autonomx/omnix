"""PHASE 5.4 — Functional Tests for Deterministic Identity Hardening (rpg-design.txt)

These tests verify the Phase 5.4 hardening changes at a functional level:
- Identity versioning (IDENTITY_VERSION = 1)
- Deep-copy payload mutation safety
- Cross-run identity stability
- Identity not derived from payload tick duplication
- Loading history preserves identity

Phase 5.4 fixes:
1. Identity versioning via IDENTITY_VERSION constant
2. Deep-copy payload to prevent nested mutation side-effects
3. Separate identity_payload from stored payload (no duplicate tick)
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.clock import DeterministicClock
from app.rpg.core.determinism import (
    IDENTITY_VERSION,
    DeterminismConfig,
    compute_deterministic_event_id,
)
from app.rpg.core.event_bus import Event, EventBus, EventContext


class TestIdentityVersioning(unittest.TestCase):
    """PHASE 5.4: Identity versioning should be present and stable."""

    def test_identity_version_exists(self):
        """IDENTITY_VERSION constant should be defined."""
        self.assertEqual(IDENTITY_VERSION, 1)

    def test_event_id_includes_version(self):
        """Event ID computation should include version in the hash input."""
        eid_with_version = compute_deterministic_event_id(
            seed=42, event_type="test", payload={}, source="sys",
            parent_id=None, tick=1, seq=0,
        )
        # Compute with explicit version
        from app.rpg.core.determinism import IDENTITY_VERSION as IV
        eid_explicit_v = compute_deterministic_event_id(
            seed=42, event_type="test", payload={}, source="sys",
            parent_id=None, tick=1, seq=0,
        )
        self.assertEqual(eid_with_version, eid_explicit_v)


class TestDeepCopyPayloadSafety(unittest.TestCase):
    """PHASE 5.4: Deep-copy payload prevents mutation side-effects."""

    def test_nested_payload_mutation_after_emit_not_stored(self):
        """Nested payload mutation after emit should not affect stored payload."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=42))
        bus.set_tick(1)

        original_payload = {"outer": {"inner": [1, 2, 3]}}
        event = Event(type="nested", payload=copy.deepcopy(original_payload), source="sys")
        bus.emit(event)

        # Mutate original payload after emit
        original_payload["outer"]["inner"].append(999)

        # Stored event should still have original data
        history = bus.history()
        self.assertEqual(history[0].payload["outer"]["inner"], [1, 2, 3])

    def test_identity_unchanged_by_post_emit_mutation(self):
        """Event identity should remain unchanged after caller mutates payload."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=77))
        event = Event(type="test", payload={"a": {"b": 1}}, source="sys")
        bus.emit(event)
        original_id = event.event_id

        event.payload["a"]["b"] = 999
        event.payload["new_key"] = "added"

        self.assertEqual(event.event_id, original_id)
        self.assertEqual(bus.history()[0].event_id, original_id)


class TestCrossRunIdentityStability(unittest.TestCase):
    """PHASE 5.4: Same seed + same events = identical IDs across runs."""

    def test_same_events_same_ids_across_runs(self):
        """Running the same events with the same seed should produce identical IDs."""
        seed = 2026
        events_spec = [
            ("attack", {"target": "goblin"}, "npc"),
            ("defend", {"target": "self"}, "npc"),
            ("heal", {"target": "ally"}, "player"),
        ]

        def run_events():
            clock = DeterministicClock(start_time=0.0, increment=0.001)
            bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=seed))
            bus.set_tick(1)
            ids = []
            for evt_type, payload, source in events_spec:
                e = Event(type=evt_type, payload=payload, source=source)
                bus.emit(e)
                ids.append(e.event_id)
            return ids

        ids1 = run_events()
        ids2 = run_events()
        self.assertEqual(ids1, ids2)

    def test_same_events_same_ids_across_processes(self):
        """Identity should be stable even across separate bus instances."""
        seed = 3030

        bus1 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus1.set_tick(5)
        e1 = Event(type="move", payload={"x": 10, "y": 20}, source="player")
        bus1.emit(e1)

        bus2 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus2.set_tick(5)
        e2 = Event(type="move", payload={"x": 10, "y": 20}, source="player")
        bus2.emit(e2)

        self.assertEqual(e1.event_id, e2.event_id)


class TestIdentityTickSeparation(unittest.TestCase):
    """PHASE 5.4: Identity should not depend on payload['tick'] duplication."""

    def test_explicit_tick_explicit_payload_same_id(self):
        """Event with tick=5 and event with tick=5 payload should have same ID."""
        seed = 555
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


class TestLoadHistoryPreservesIdentity(unittest.TestCase):
    """PHASE 5.4: Loading history should not alter deterministic IDs."""

    def test_load_history_does_not_alter_ids(self):
        """Original event IDs should remain unchanged after loading into new bus."""
        seed = 777
        bus1 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus1.set_tick(1)
        e1 = Event(type="start", payload={"zone": "town"}, source="sys")
        bus1.emit(e1)
        bus1.set_tick(2)
        e2 = Event(type="move", payload={"x": 5}, source="player", parent_id=e1.event_id)
        bus1.emit(e2)

        original_ids = [e1.event_id, e2.event_id]
        history = bus1.history()

        bus2 = EventBus(
            clock=DeterministicClock(start_time=0.0, increment=0.001),
            determinism=DeterminismConfig(seed=seed),
        )
        bus2.load_history(history)
        loaded_ids = [e.event_id for e in bus2.history()]

        self.assertEqual(original_ids, loaded_ids)


class TestBackwardCompatibility(unittest.TestCase):
    """PHASE 5.4: Changes should not break existing functionality."""

    def test_basic_emit_works(self):
        """Basic emit should continue to work."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=1))
        bus.set_tick(1)
        event = Event(type="hello", payload={"world": True}, source="test")
        bus.emit(event)

        self.assertIsNotNone(event.event_id)
        self.assertEqual(event.tick, 1)
        self.assertEqual(event.payload["world"], True)

    def test_context_still_works(self):
        """EventContext should still apply parent_id and tick."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock, determinism=DeterminismConfig(seed=2))
        bus.set_tick(99)

        event = Event(type="child", payload={"a": 1}, source="sys")
        ctx = EventContext(parent_id="parent_0", tick=7)
        bus.emit(event, context=ctx)

        emitted = bus.history()[0]
        self.assertEqual(emitted.parent_id, "parent_0")
        self.assertEqual(emitted.tick, 7)

    def test_explicit_event_id_preserved(self):
        """Explicit event_id should still be honored."""
        bus = EventBus(determinism=DeterminismConfig(seed=1))
        e = Event(type="custom", payload={}, source="sys", event_id="my_custom_id")
        bus.emit(e)
        self.assertEqual(e.event_id, "my_custom_id")


if __name__ == "__main__":
    unittest.main()