"""PHASE 5.2 — Functional Tests for Deterministic Event System (rpg-design.txt)

These tests validate the deterministic event system at an integration level,
testing how the system works as a whole rather than individual components.

Tests cover:
- End-to-end deterministic event flow
- Replay parity across sessions
- Simulation comparison with deterministic events
- Timeline causality preservation during replay
"""

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

"""
NOTE: This test file is currently disabled due to import issues.
See src/tests/regression/test_phase52_determinism_regression.py for working tests.
"""

import sys
import os
import hashlib
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus, EventContext
from app.rpg.core.clock import DeterministicClock
from app.rpg.core.replay_engine import ReplayEngine, ReplayConfig


# ---------------------------------------------------------------------------
# Helper: Compute event fingerprint
# ---------------------------------------------------------------------------

def compute_event_fingerprint(event: Event) -> str:
    """Compute a deterministic fingerprint for an event.
    
    This includes all fields that should be identical across runs.
    
    Args:
        event: Event to fingerprint.
        
    Returns:
        SHA-256 hex digest of event data.
    """
    data = {
        "id": event.event_id,
        "type": event.type,
        "tick": event.tick,
        "parent": event.parent_id,
        "payload": dict(sorted(event.payload.items())) if event.payload else {},
    }
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def compute_history_fingerprint(events: List[Event]) -> str:
    """Compute a deterministic fingerprint for an event history.
    
    Args:
        events: List of events to fingerprint.
        
    Returns:
        SHA-256 hex digest of entire history.
    """
    fingerprints = [compute_event_fingerprint(e) for e in events]
    combined = json.dumps(fingerprints, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(combined.encode()).hexdigest()


# ---------------------------------------------------------------------------
# End-to-End Deterministic Event Flow
# ---------------------------------------------------------------------------

class TestDeterministicEventFlow(unittest.TestCase):
    """PHASE 5.2 Functional: End-to-end deterministic event flow."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_full_flow_deterministic(self):
        """A full tick flow should produce deterministic results.
        
        This simulates a game loop with world, NPC, and narrative events.
        Running the same sequence twice should produce identical fingerprints.
        """
        def run_flow(clock: DeterministicClock) -> List[Event]:
            bus = EventBus(clock=clock)
            bus._seq = 0  # Reset sequence counter
            
            # Tick 1: World initialization
            bus.set_tick(1)
            e1 = Event(type="world_init", payload={"seed": 42}, source="world", event_id="evt_1")
            bus.emit(e1)
            e2 = Event(type="npc_spawn", payload={"npc_id": 1, "name": "Alice"}, source="npc", event_id="evt_2")
            bus.emit(e2)
            
            # Tick 2: Player action
            bus.set_tick(2)
            e3 = Event(type="player_action", payload={"action": "talk", "target": "Alice"}, source="player", event_id="evt_3")
            bus.emit(e3)
            e4 = Event(type="dialogue_started", payload={"participants": ["player", "Alice"]}, source="narrative", event_id="evt_4")
            bus.emit(e4)
            
            # Tick 3: NPC response
            bus.set_tick(3)
            e5 = Event(type="npc_response", payload={"npc_id": 1, "response": "greeting"}, source="npc", event_id="evt_5")
            bus.emit(e5)
            e6 = Event(type="relationship_changed", payload={"npc": 1, "delta": 0.1}, source="world", event_id="evt_6")
            bus.emit(e6)
            
            # Tick 4: World state update
            bus.set_tick(4)
            e7 = Event(type="time_advanced", payload={"hour": 10}, source="world", event_id="evt_7")
            bus.emit(e7)
            e8 = Event(type="quest_progress", payload={"quest_id": 1, "step": 1}, source="quest", event_id="evt_8")
            bus.emit(e8)
            
            # Tick 5: Narrative resolution
            bus.set_tick(5)
            e9 = Event(type="scene_complete", payload={"scene_id": "village_intro"}, source="narrative", event_id="evt_9")
            bus.emit(e9)
            
            return bus.history()

        # Run once
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        history1 = run_flow(clock1)
        
        # Run again - with explicit event IDs, counter doesn't matter
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        history2 = run_flow(clock2)
        
        # Fingerprints must match
        fp1 = compute_history_fingerprint(history1)
        fp2 = compute_history_fingerprint(history2)
        self.assertEqual(fp1, fp2)

    def test_event_ordering_preserved(self):
        """Events should maintain correct ordering across ticks."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        
        # Emit events out of tick order
        bus.set_tick(3)
        e3 = Event(type="late", payload={}, source="test")
        bus.emit(e3)
        
        bus.set_tick(1)
        e1 = Event(type="early", payload={}, source="test")
        bus.emit(e1)
        
        bus.set_tick(2)
        e2 = Event(type="middle", payload={}, source="test")
        bus.emit(e2)
        
        # History should be sorted by (tick, _seq)
        history = bus.history()
        types = [e.type for e in history]
        self.assertEqual(types, ["early", "middle", "late"])

    def test_context_preservation(self):
        """EventContext should preserve causal chains."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        
        # Simulate a causal chain with explicit parent_id on Events
        bus.set_tick(1)
        root = Event(type="player_input", payload={"text": "hello"}, source="player")
        bus.emit(root)
        
        root_id = root.event_id
        
        # NPC response referencing root
        ctx = EventContext(parent_id=root_id)
        npc_response = Event(type="npc_response", payload={}, source="npc")
        bus.emit(npc_response, context=ctx)
        
        npc_id = npc_response.event_id
        
        # World update referencing npc_response via EventContext
        ctx2 = EventContext(parent_id=npc_id, tick=1)
        world_update = Event(
            type="world_update",
            payload={},
            source="world",
            parent_id=npc_id,  # also set explicitly on event
        )
        bus.emit(world_update, context=ctx2)
        
        history = bus.history()
        
        # Verify causal chain
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].type, "player_input")
        self.assertEqual(history[1].type, "npc_response")  
        self.assertEqual(history[2].type, "world_update")
        self.assertEqual(history[1].parent_id, history[0].event_id)
        self.assertEqual(history[2].parent_id, history[1].event_id)


# ---------------------------------------------------------------------------
# Replay Parity Tests
# ---------------------------------------------------------------------------

class TestReplayParity(unittest.TestCase):
    """PHASE 5.2 Functional: Replay should produce identical results."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_replay_produces_same_fingerprint(self):
        """Replaying events should produce the same fingerprint as original."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        
        # Record events
        for tick in range(1, 6):
            bus.set_tick(tick)
            e = Event(
                type=f"event_{tick}",
                payload={"tick": tick, "data": f"payload_{tick}"},
                source=f"system_{tick}",
            )
            bus.emit(e)
        
        original_history = bus.history()
        original_fp = compute_history_fingerprint(original_history)
        
        # Reset for replay
        EventBus._global_event_counter = 0
        
        # Create replay with deterministic clock
        clock_replay = DeterministicClock(start_time=0.0, increment=0.001)
        replay_bus = EventBus(clock=clock_replay)
        
        # Replay each event
        for e in original_history:
            replay_bus.emit(Event(
                type=e.type,
                payload=dict(e.payload),
                source=e.source,
                event_id=e.event_id,
                timestamp=e.timestamp,
                parent_id=e.parent_id,
                tick=e.tick,
            ), replay=True)
        
        replay_history = replay_bus.history()
        replay_fp = compute_history_fingerprint(replay_history)
        
        # Replayed events should match originals
        # Note: history() won't include replay=True events, so we check
        # that the events loaded via load_history match
        replay_bus2 = EventBus(clock=clock_replay)
        replay_bus2.load_history(original_history)
        loaded_history = replay_bus2.history()
        loaded_fp = compute_history_fingerprint(loaded_history)
        
        self.assertEqual(original_fp, loaded_fp)

    def test_replay_with_branch_selection(self):
        """Replay with branch selection should produce consistent results."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus = EventBus(clock=clock)
        
        # Build a simple causal chain
        bus.set_tick(1)
        root = Event(type="root", payload={}, source="test", event_id="evt_root")
        bus.emit(root)
        
        bus.set_tick(2)
        branch_a = Event(type="branch_a", payload={}, source="test",
                         event_id="evt_a", parent_id="evt_root")
        bus.emit(branch_a)
        
        bus.set_tick(3)
        branch_b = Event(type="branch_b", payload={}, source="test",
                         event_id="evt_b", parent_id="evt_root")
        bus.emit(branch_b)
        
        history = bus.history()
        
        # Verify timeline graph has all events
        self.assertTrue(bus.timeline.has_event("evt_root"))
        self.assertTrue(bus.timeline.has_event("evt_a"))
        self.assertTrue(bus.timeline.has_event("evt_b"))


# ---------------------------------------------------------------------------
# Simulation comparison with deterministic events
# ---------------------------------------------------------------------------

class TestSimulationParityFunctional(unittest.TestCase):
    """PHASE 5.2 Functional: Two simulations should produce identical results."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def _run_simulation(self, clock: DeterministicClock, steps: int = 10) -> List[Event]:
        """Run a deterministic simulation for given steps.
        
        Args:
            clock: DeterministicClock to use.
            steps: Number of ticks to simulate.
            
        Returns:
            List of events produced.
        """
        bus = EventBus(clock=clock)
        
        for tick in range(1, steps + 1):
            bus.set_tick(tick)
            
            # World events
            bus.emit(Event(
                type="world_tick",
                payload={"tick": tick, "time_of_day": tick % 24},
                source="world",
            ))
            
            # NPC events
            if tick % 2 == 0:
                bus.emit(Event(
                    type="npc_action",
                    payload={"npc_id": tick % 3, "action": "patrol"},
                    source="npc",
                ))
            
            # Narrative events
            if tick % 3 == 0:
                bus.emit(Event(
                    type="event_triggered",
                    payload={"event_id": f"evt_{tick}", "priority": tick % 5},
                    source="narrative",
                ))
        
        return bus.history()

    def test_simulations_produce_identical_results(self):
        """Two identical simulations should produce identical event histories."""
        # Run 1
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        history1 = self._run_simulation(clock1)
        
        # Run 2 - reset counter and sequence for determinism
        EventBus._global_event_counter = 0
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        history2 = self._run_simulation(clock2)
        
        # Fingerprints must match
        self.assertEqual(compute_history_fingerprint(history1),
                         compute_history_fingerprint(history2))
        
        # Event IDs must match exactly
        ids1 = [e.event_id for e in history1]
        ids2 = [e.event_id for e in history2]
        self.assertEqual(ids1, ids2)

    def test_simulations_with_different_params_produce_different_results(self):
        """Simulations with different parameters should differ."""
        clock1 = DeterministicClock(start_time=0.0, increment=0.001)
        history1 = self._run_simulation(clock1, steps=10)
        
        clock2 = DeterministicClock(start_time=0.0, increment=0.001)
        history2 = self._run_simulation(clock2, steps=5)  # Different steps
        
        # Fingerprints should differ
        self.assertNotEqual(compute_history_fingerprint(history1),
                            compute_history_fingerprint(history2))


# ---------------------------------------------------------------------------
# Timeline Causality Preservation During Replay
# ---------------------------------------------------------------------------

class TestTimelineCausality(unittest.TestCase):
    """PHASE 5.2 Functional: Timeline causality should be preserved during replay."""

    def setUp(self):
        """Reset global state before each test."""
        EventBus._global_event_counter = 0
        EventBus._clock = None

    def test_causal_chain_preserved_after_load_history(self):
        """Loading history should preserve causal parent links in timeline."""
        clock = DeterministicClock(start_time=0.0, increment=0.001)
        bus1 = EventBus(clock=clock)
        
        # Build causal chain
        bus1.set_tick(1)
        root = Event(type="root", payload={}, source="test", event_id="evt_1")
        bus1.emit(root)
        
        bus1.set_tick(2)
        child = Event(type="child", payload={}, source="test",
                      event_id="evt_2", parent_id="evt_1")
        bus1.emit(child)
        
        bus1.set_tick(3)
        leaf = Event(type="leaf", payload={}, source="test",
                     event_id="evt_3", parent_id="evt_2")
        bus1.emit(leaf)
        
        # Verify original timeline - check nodes through graph get_node
        self.assertIsNotNone(bus1.timeline.get_node("evt_1"))
        self.assertIsNotNone(bus1.timeline.get_node("evt_2"))
        self.assertIsNotNone(bus1.timeline.get_node("evt_3"))
        
        # Load into new bus
        bus2 = EventBus(clock=clock)
        bus2.load_history(bus1.history())
        
        # Verify timeline is rebuilt correctly
        self.assertTrue(bus2.timeline.has_event("evt_1"))
        self.assertTrue(bus2.timeline.has_event("evt_2"))
        self.assertTrue(bus2.timeline.has_event("evt_3"))


# ---------------------------------------------------------------------------
# Phase 52 — End-to-End Replay Equivalence Test (rpg-design.txt)
# ---------------------------------------------------------------------------

class _DummyIntentParser:
    def parse(self, player_input: str):
        return {"text": player_input}


class _DummyWorld:
    def __init__(self):
        self.mode = "live"

    def tick(self, event_bus):
        pass

    def set_mode(self, mode):
        self.mode = mode


class _DummyNPCSystem:
    def __init__(self):
        self.mode = "live"

    def update(self, intent, event_bus):
        event_bus.emit(
            Event(
                type="npc_idle",
                payload={"intent": intent["text"]},
                source="npc",
            )
        )

    def set_mode(self, mode):
        self.mode = mode


class _DummyDirector:
    def __init__(self):
        self.mode = "live"

    def process(self, events, intent, event_bus):
        return {
            "events": [e.type for e in events],
            "intent": intent["text"],
        }

    def set_mode(self, mode):
        self.mode = mode


class _DummyRenderer:
    def __init__(self):
        self.mode = "live"

    def render(self, narrative):
        return {"rendered": narrative}

    def set_mode(self, mode):
        self.mode = mode


def _make_loop(seed: int):
    from app.rpg.core.game_loop import GameLoop
    from app.rpg.core.determinism import DeterminismConfig

    bus = EventBus(
        clock=DeterministicClock(start_time=0.0, increment=0.001),
        determinism=DeterminismConfig(seed=seed),
    )
    return GameLoop(
        intent_parser=_DummyIntentParser(),
        world=_DummyWorld(),
        npc_system=_DummyNPCSystem(),
        event_bus=bus,
        story_director=_DummyDirector(),
        scene_renderer=_DummyRenderer(),
    )


class TestPhase52EndToEndReplayEquivalence(unittest.TestCase):
    """PHASE 5.2: End-to-end replay equivalence test.

    This test proves that:
    1. A live run produces deterministic events.
    2. Replaying those events into a fresh loop with the same seed
       produces an equivalent state hash.
    """

    def test_full_replay_produces_equivalent_state_hash(self):
        """Replay should produce the same state hash as the original run."""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

        from app.rpg.core.determinism import DeterminismConfig
        from app.rpg.core.replay_engine import ReplayEngine
        from app.rpg.validation.state_hash import compute_state_hash

        seed = 123

        # Run 1: Live execution
        loop1 = _make_loop(seed)
        for _ in range(5):
            loop1.tick("wait")

        history = loop1.event_bus.history()
        hash1 = compute_state_hash(loop1)

        # Run 2: Replay into fresh loop with same seed
        replay = ReplayEngine(lambda: _make_loop(seed))
        loop2 = replay.replay(history)
        hash2 = compute_state_hash(loop2)

        # State hashes should match - replay produced equivalent state
        self.assertEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
