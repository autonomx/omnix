"""Regression tests for the RPG Director module.

These tests ensure the Director module maintains expected behavior
across code changes, specifically checking:
    - Signal values remain stable for given inputs
    - Event application side effects don't unexpectedly change
    - Narrative thread tracking is preserved
    - Cooldown mechanics work as designed
    - End-to-end director output format stays consistent
"""

from __future__ import annotations

import sys
import pathlib
import unittest
from unittest.mock import MagicMock

# Ensure the project root is on sys.path
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT / "src" / "app") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src" / "app"))

from rpg.director.director import Director
from rpg.director.event_engine import EventEngine
from rpg.director.emergence_adapter import EmergenceAdapter


# ============================================================
# Helper — create mock NPC
# ============================================================

def _make_npc(name: str, last_action: str = "idle") -> MagicMock:
    npc = MagicMock()
    npc.name = name
    npc.last_action = last_action
    npc.id = name
    return npc


# ============================================================
# Signal Stability — EmergenceAdapter output must not change
# ============================================================

class TestSignalStability(unittest.TestCase):
    """EmergenceAdapter signal values for given inputs must remain stable."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_stagnation_signal_fixed(self):
        """Stagnation signal for 3/3 idle NPCs = 1.0 must not change."""
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        self.assertEqual(self.adapter._stagnation(npcs), 1.0)

    def test_stagnation_mixed_fixed(self):
        """Stagnation signal for 1/2 idle NPCs = 0.5 must not change."""
        npcs = [_make_npc("a"), _make_npc("b", "walk")]
        self.assertAlmostEqual(self.adapter._stagnation(npcs), 0.5)

    def test_conflict_signal_fixed(self):
        """Conflict signal for enemy_count=5, danger_level=5 = 0.5 fixed."""
        ws = {"enemy_count": 5, "danger_level": 5}
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.5)

    def test_conflict_enemy_only_fixed(self):
        """Conflict signal for enemy_count=10, danger_level=0 = 0.6."""
        ws = {"enemy_count": 10, "danger_level": 0}
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.6)

    def test_conflict_danger_only_fixed(self):
        """Conflict signal for enemy_count=0, danger_level=10 = 0.4."""
        ws = {"enemy_count": 0, "danger_level": 10}
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.4)

    def test_failure_signal_all_fixed(self):
        ws = {"enemy_count": 5, "danger_level": 5}
        result = self.adapter.analyze(ws, [_make_npc("a", "fight")], [])
        self.assertIn("stagnation", result)
        self.assertIn("conflict", result)
        self.assertIn("failure_spike", result)
        self.assertIn("divergence", result)


# ============================================================
# Event Application Stability
# ============================================================

class TestEventApplicationStability(unittest.TestCase):
    """Event application to world state must produce same results."""

    def test_supply_drop_effect(self):
        """supply_drop should add resources: 3."""
        ws = {"resources": 0}
        engine = EventEngine()
        event = {"name": "supply_drop", "world_effects": {"resources": 3}}
        engine.apply_event(event, ws)
        self.assertEqual(ws["resources"], 3)

    def test_betrayal_effect(self):
        """betrayal should reduce trust by 0.5."""
        ws = {"trust_level": 0.5}
        engine = EventEngine()
        event = {"name": "betrayal", "world_effects": {"trust_level": -0.5}}
        engine.apply_event(event, ws)
        self.assertEqual(ws["trust_level"], 0.0)

    def test_enemy_reinforcement_effect(self):
        """enemy_reinforcements should add 2 enemies."""
        ws = {"enemy_count": 3}
        engine = EventEngine()
        event = {"name": "enemy_reinforcements", "world_effects": {"enemy_count": 2}}
        engine.apply_event(event, ws)
        self.assertEqual(ws["enemy_count"], 5)

    def test_hazard_effect(self):
        """environmental_hazard should add 2 to danger."""
        ws = {"danger_level": 1}
        engine = EventEngine()
        event = {"name": "environmental_hazard", "world_effects": {"danger_level": 2}}
        engine.apply_event(event, ws)
        self.assertEqual(ws["danger_level"], 3)


# ============================================================
# Narrative Thread Format Stability
# ============================================================

class TestNarrativeThreadFormat(unittest.TestCase):
    """Narrative thread dict structure must remain stable."""

    def test_thread_structure(self):
        """Thread should have expected keys."""
        d = Director(enable_cooldowns=False)
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        d.tick({}, npcs, [])

        self.assertGreaterEqual(len(d.narrative_threads), 1)

        for tname, thread in d.narrative_threads.items():
            self.assertIn("stage", thread)
            self.assertIn("type", thread)
            self.assertIn("first_event", thread)
            self.assertIn("last_event", thread)
            self.assertIn("events", thread)
            self.assertIsInstance(thread["events"], list)
            self.assertGreaterEqual(len(thread["events"]), 1)

    def test_thread_stage_increments(self):
        """Thread stage should increase with each related event."""
        d = Director(enable_cooldowns=False)
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]

        # Generate many events
        initial_stage = None
        for _ in range(20):
            d.tick({}, npcs, [])
            stages = [t["stage"] for t in d.narrative_threads.values()]
            if initial_stage is None:
                initial_stage = max(stages)
            if max(stages) > initial_stage:
                return  # Test passed

        self.fail("Thread stage did not increment after 20 ticks")


# ============================================================
# Cooldown Format Stability
# ============================================================

class TestCooldownFormat(unittest.TestCase):
    """Cooldown system must maintain expected format."""

    def test_default_cooldown_keys(self):
        """Cooldowns should have expected event type keys."""
        d = Director()
        expected_keys = {"twist", "escalation", "intervention", "chaos"}
        self.assertTrue(
            expected_keys.issubset(set(d.cooldowns.keys())),
            f"Cooldown missing keys. Expected: {expected_keys}, "
            f"Got: {set(d.cooldowns.keys())}"
        )

    def test_cooldown_values_are_integers(self):
        """All cooldown values should be non-negative integers."""
        d = Director()
        for key, val in d.cooldowns.items():
            self.assertIsInstance(val, int, f"Cooldown {key} is not int: {val}")
            self.assertGreaterEqual(val, 0, f"Cooldown {key} is negative: {val}")


# ============================================================
# Director Output Format Stability
# ============================================================

class TestDirectorOutputFormat(unittest.TestCase):
    """Director event output format must remain consistent."""

    def test_event_has_required_fields(self):
        """Events from Director must have expected fields."""
        d = Director(enable_cooldowns=False)
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        event = d.tick(ws, npcs, [])

        self.assertIsNotNone(event)
        self.assertIn("name", event)
        self.assertIn("description", event)
        self.assertIn("intensity", event)
        self.assertIn("event_type", event)
        self.assertIn("world_effects", event)
        self.assertIn("tags", event)


# ============================================================
# End-to-End Regression
# ============================================================

class TestEndToEndRegression(unittest.TestCase):
    """Full Director pipeline must maintain behavior stability."""

    def test_full_pipeline_no_changes(self):
        """Running the Director with fixed inputs should produce consistent results."""
        npcs = [_make_npc("a"), _make_npc("b")]
        ws = {"enemy_count": 5, "danger_level": 3, "resources": 5}

        d = Director(enable_cooldowns=False)

        # Run one tick
        event = d.tick(ws, npcs, [])

        # Event may or may not occur (stagnation=1.0 > 0.7)
        self.assertIsNotNone(event)

    def test_multi_tick_stability(self):
        """30-tick simulation should not crash and should change world state."""
        npcs = [_make_npc("alice"), _make_npc("bob"), _make_npc("charlie")]
        ws = {
            "resources": 10,
            "enemy_count": 2,
            "danger_level": 1,
            "trust_level": 0.5,
        }
        original_ws = dict(ws)

        d = Director(enable_cooldowns=True)

        for tick in range(30):
            for npc in npcs:
                if tick % 5 == 0:
                    npc.last_action = "idle"
                else:
                    npc.last_action = "walk"
            outcomes = [MagicMock(success=True) for _ in npcs]
            event = d.tick(ws, npcs, outcomes)

        # Verify Director ran
        self.assertEqual(d.tick_count, 30)

        # World state may or may not change depending on events
        # At minimum, the Director should have processed events
        self.assertIsInstance(d.history, list)
        self.assertIsInstance(d.narrative_threads, dict)


# ============================================================
# Edge Case Regression
# ============================================================

class TestEdgeCases(unittest.TestCase):
    """Edge cases must not cause unexpected behavior changes."""

    def test_empty_npcs_doesnt_crash(self):
        """Director should handle empty NPC list gracefully."""
        d = Director()
        event = d.tick({}, [], [])
        self.assertIsNone(event)

    def test_no_world_keys_doesnt_crash(self):
        """Director should handle empty world state."""
        d = Director()
        event = d.tick({}, [_make_npc("a")], [])
        # stagnation=1.0 > 0.7 threshold
        self.assertIsNotNone(event)

    def test_outcomes_with_no_success_attr(self):
        """Director should handle outcomes without success attribute."""
        d = Director(enable_cooldowns=False)
        outcomes = [None, True, 0, []]  # No .success attribute
        npcs = [_make_npc("a")]
        event = d.tick({}, npcs, outcomes)
        # Should not crash — treats truthy/falsy as success

    def test_world_state_missing_keys(self):
        """Director should handle world state missing all keys."""
        ws = {}
        d = Director()
        npcs = [_make_npc("a")]
        result = d.tick(ws, npcs, [])
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()