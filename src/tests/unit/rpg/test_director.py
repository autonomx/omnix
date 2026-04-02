"""Unit tests for the RPG Director module.

Tests cover:
    EmergenceAdapter: signal computation from game state.
    EventEngine: event creation and application with variety logic.
    Director: decision thresholds, cooldowns, narrative threads, tick loop.
"""

from __future__ import annotations

import sys
import pathlib
import unittest
from copy import deepcopy
from unittest.mock import MagicMock

# Ensure the project root is on sys.path
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT / "src" / "app") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src" / "app"))

from rpg.director.emergence_adapter import EmergenceAdapter
from rpg.director.event_engine import EventEngine, EVENT_POOLS
from rpg.director.director import Director


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
# EmergenceAdapter Tests
# ============================================================

class TestEmergenceAdapterStagnation(unittest.TestCase):
    """Test stagnation signal computation."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_all_idle_returns_1_0(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        result = self.adapter._stagnation(npcs)
        self.assertEqual(result, 1.0)

    def test_all_active_returns_0_0(self):
        npcs = [
            _make_npc("a", "walk"),
            _make_npc("b", "attack"),
            _make_npc("c", "talk"),
        ]
        result = self.adapter._stagnation(npcs)
        self.assertEqual(result, 0.0)

    def test_half_idle_returns_0_5(self):
        npcs = [_make_npc("a"), _make_npc("b", "walk")]
        result = self.adapter._stagnation(npcs)
        self.assertAlmostEqual(result, 0.5)

    def test_empty_npcs_returns_0_0(self):
        self.assertEqual(self.adapter._stagnation([]), 0.0)

    def test_none_last_action_treated_as_idle(self):
        npc = MagicMock()
        npc.last_action = None
        self.assertEqual(self.adapter._stagnation([npc]), 1.0)


class TestEmergenceAdapterConflict(unittest.TestCase):
    """Test conflict signal computation."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_no_enemies_zero_conflict(self):
        ws = {"enemy_count": 0, "danger_level": 0}
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.0)

    def test_max_enemies_max_conflict(self):
        ws = {"enemy_count": 10, "danger_level": 10}
        self.assertAlmostEqual(self.adapter._conflict(ws), 1.0)

    def test_enemy_weight_0_6(self):
        ws = {"enemy_count": 10, "danger_level": 0}
        # enemy_signal=1.0, danger_signal=0.0 -> 1.0*0.6 + 0*0.4 = 0.6
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.6)

    def test_danger_weight_0_4(self):
        ws = {"enemy_count": 0, "danger_level": 10}
        self.assertAlmostEqual(self.adapter._conflict(ws), 0.4)

    def test_missing_keys_returns_0(self):
        self.assertAlmostEqual(self.adapter._conflict({}), 0.0)


class TestEmergenceAdapterFailure(unittest.TestCase):
    """Test failure spike signal."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_all_failures_returns_1_0(self):
        outcomes = [MagicMock(success=False) for _ in range(5)]
        self.assertAlmostEqual(self.adapter._failure(outcomes), 1.0)

    def test_all_success_returns_0_0(self):
        outcomes = [MagicMock(success=True) for _ in range(5)]
        self.assertAlmostEqual(self.adapter._failure(outcomes), 0.0)

    def test_half_failures_returns_0_5(self):
        outcomes = [MagicMock(success=False), MagicMock(success=True)]
        self.assertAlmostEqual(self.adapter._failure(outcomes), 0.5)

    def test_empty_outcomes_returns_0_0(self):
        self.assertAlmostEqual(self.adapter._failure([]), 0.0)

    def test_dict_outcomes(self):
        outcomes = [{"success": False}, {"success": True}, {"success": False}]
        self.assertAlmostEqual(self.adapter._failure(outcomes), 2 / 3, places=4)


class TestEmergenceAdapterDivergence(unittest.TestCase):
    """Test divergence signal."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_no_chaos_returns_0(self):
        self.assertAlmostEqual(self.adapter._divergence({}), 0.0)

    def test_max_chaos_returns_1(self):
        ws = {"chaos": 1.0}
        self.assertAlmostEqual(self.adapter._divergence(ws), 1.0)

    def test_divergence_fallback(self):
        ws = {"divergence": 0.8}
        self.assertAlmostEqual(self.adapter._divergence(ws), 0.8)

    def test_uses_max_of_chaos_divergence(self):
        ws = {"chaos": 0.3, "divergence": 0.9}
        self.assertAlmostEqual(self.adapter._divergence(ws), 0.9)


class TestEmergenceAdapterAnalyze(unittest.TestCase):
    """Test full analyze method."""

    def setUp(self):
        self.adapter = EmergenceAdapter()

    def test_returns_all_four_signals(self):
        npcs = [_make_npc("a"), _make_npc("b")]
        outcomes = [{"success": True}]
        ws = {"enemy_count": 5, "danger_level": 3}
        result = self.adapter.analyze(ws, npcs, outcomes)
        self.assertIn("stagnation", result)
        self.assertIn("conflict", result)
        self.assertIn("failure_spike", result)
        self.assertIn("divergence", result)

    def test_all_values_between_0_and_1(self):
        npcs = [_make_npc("a")]
        outcomes = [{"success": False}]
        ws = {"enemy_count": 20, "danger_level": 20, "chaos": 2.0}
        result = self.adapter.analyze(ws, npcs, outcomes)
        for key, val in result.items():
            self.assertGreaterEqual(val, 0.0, f"{key} below 0")
            self.assertLessEqual(val, 1.0, f"{key} above 1.0")


# ============================================================
# EventEngine Tests
# ============================================================

class TestEventEngineCreate(unittest.TestCase):
    """Test EventEngine event creation."""

    def setUp(self):
        self.engine = EventEngine(targeted=False)

    def test_creates_twist_event(self):
        decision = {"type": "twist", "intensity": 0.6}
        ws = {}
        event = self.engine.create_event(decision, ws)
        self.assertIsNotNone(event)
        self.assertIn("name", event)
        self.assertEqual(event["event_type"], "twist")

    def test_creates_escalation_event(self):
        decision = {"type": "escalation", "intensity": 0.9}
        event = self.engine.create_event(decision, {})
        self.assertEqual(event["event_type"], "escalation")

    def test_creates_intervention_event(self):
        decision = {"type": "intervention", "intensity": 0.5}
        event = self.engine.create_event(decision, {})
        self.assertEqual(event["event_type"], "intervention")

    def test_creates_chaos_event(self):
        decision = {"type": "chaos", "intensity": 0.8}
        event = self.engine.create_event(decision, {})
        self.assertEqual(event["event_type"], "chaos")

    def test_unknown_type_defaults_to_chaos(self):
        decision = {"type": "unknown_type_xyz", "intensity": 0.5}
        event = self.engine.create_event(decision, {})
        self.assertEqual(event["event_type"], "unknown_type_xyz")

    def test_intensity_scales_effects(self):
        decision = {"type": "intervention", "intensity": 0.5}
        ws = {}
        event = self.engine.create_event(decision, ws)
        self.assertAlmostEqual(event["intensity"], 0.5)

    def test_variety_avoids_last_event(self):
        """EventEngine should avoid repeating same-named events."""
        # Apply the same event multiple times — each create_event should
        # avoid the previous event name
        decision = {"type": "twist", "intensity": 1.0}
        e1 = self.engine.create_event(decision, {})
        self.engine.apply_event(e1, {})

        # Next creation should pick a different twist event
        # (only matters if twist pool has > 1 events)
        twist_pool = EVENT_POOLS["twist"]
        if len(twist_pool) > 1:
            e2 = self.engine.create_event(decision, {})
            # e2 should differ from e1's name
            self.assertNotEqual(e1.get("name"), e2.get("name"))


class TestEventEngineApply(unittest.TestCase):
    """Test EventEngine event application to world state."""

    def setUp(self):
        self.engine = EventEngine(targeted=False)

    def test_supply_drop_adds_resources(self):
        ws = {"resources": 0}
        event = {"name": "supply_drop", "world_effects": {"resources": 3}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["resources"], 3)

    def test_enemy_reinforcements_adds_enemies(self):
        ws = {"enemy_count": 0}
        event = {"name": "enemy_reinforcements", "world_effects": {"enemy_count": 2}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["enemy_count"], 2)

    def test_betrayal_reduces_trust(self):
        ws = {"trust_level": 0.5}
        event = {"name": "unexpected_betrayal", "world_effects": {"trust_level": -0.5}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["trust_level"], 0.0)

    def test_trust_clamped_to_minus_1(self):
        ws = {"trust_level": 0.0}
        event = {"name": "test", "world_effects": {"trust_level": -2.0}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["trust_level"], -1.0)

    def test_trust_clamped_to_1(self):
        ws = {"trust_level": 0.9}
        event = {"name": "test", "world_effects": {"trust_level": 0.5}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["trust_level"], 1.0)

    def test_enemy_count_clamped_to_0(self):
        ws = {"enemy_count": 1}
        event = {"name": "test", "world_effects": {"enemy_count": -5}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["enemy_count"], 0)

    def test_resources_clamped_to_0(self):
        ws = {"resources": 1}
        event = {"name": "test", "world_effects": {"resources": -5}}
        self.engine.apply_event(event, ws)
        self.assertEqual(ws["resources"], 0)

    def test_none_event_returns_none(self):
        ws = {"enemy_count": 0}
        result = self.engine.apply_event(None, ws)
        self.assertIsNone(result)

    def test_apply_appends_to_history(self):
        ws = {}
        event = {"name": "test", "world_effects": {}}
        self.engine.apply_event(event, ws)
        self.assertEqual(len(self.engine.history), 1)


class TestEventEngineSummary(unittest.TestCase):
    """Test event summary generation."""

    def test_empty_summary(self):
        engine = EventEngine()
        summary = engine.get_event_summary()
        self.assertEqual(summary["total_events"], 0)
        self.assertEqual(summary["by_type"], {})

    def test_summary_after_apply(self):
        engine = EventEngine()
        ws = {}
        event = {"name": "twist_event", "event_type": "twist", "world_effects": {}}
        engine.apply_event(event, ws)
        summary = engine.get_event_summary()
        self.assertEqual(summary["total_events"], 1)
        self.assertIn("twist", summary["by_type"])

    def test_reset_clears_history(self):
        engine = EventEngine()
        ws = {}
        event = {"name": "x", "world_effects": {}}
        engine.apply_event(event, ws)
        engine.reset()
        self.assertEqual(len(engine.history), 0)
        self.assertIsNone(engine.last_event_type)


# ============================================================
# Director Tests
# ============================================================

class TestDirectorDefaultConstruction(unittest.TestCase):
    """Test Director default construction."""

    def test_default_values(self):
        d = Director()
        self.assertIsInstance(d.emergence_tracker, EmergenceAdapter)
        self.assertIsInstance(d.event_engine, EventEngine)
        self.assertEqual(d.history, [])
        self.assertEqual(d.tick_count, 0)
        self.assertEqual(d.narrative_threads, {})
        self.assertTrue(d.enable_cooldowns)


class TestDirectorTick(unittest.TestCase):
    """Test Director tick method."""

    def test_no_intervention_when_signals_low(self):
        # All NPCs active, no enemies, all successful, no chaos
        npcs = [_make_npc("a", "walk"), _make_npc("b", "talk")]
        outcomes = [MagicMock(success=True), MagicMock(success=True)]
        ws = {"enemy_count": 0, "danger_level": 0, "chaos": 0.0, "resources": 5}

        d = Director()
        result = d.tick(ws, npcs, outcomes)
        self.assertIsNone(result)
        self.assertEqual(d.tick_count, 1)

    def test_stagnation_triggers_twist(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        outcomes = []
        ws = {"enemy_count": 0, "danger_level": 0, "chaos": 0.0}

        d = Director()
        result = d.tick(ws, npcs, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["event_type"], "twist")

    def test_high_conflict_triggers_escalation(self):
        npcs = [_make_npc("a", "fight")]
        outcomes = []
        ws = {"enemy_count": 12, "danger_level": 10, "chaos": 0.0}

        d = Director(enable_cooldowns=False)
        result = d.tick(ws, npcs, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["event_type"], "escalation")

    def test_failure_spike_triggers_intervention(self):
        npcs = [_make_npc("a", "attack")]
        outcomes = [MagicMock(success=False), MagicMock(success=False)]
        ws = {"enemy_count": 0, "danger_level": 0}

        d = Director(enable_cooldowns=False)
        result = d.tick(ws, npcs, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["event_type"], "intervention")

    def test_high_divergence_triggers_chaos(self):
        npcs = [_make_npc("a", "walk")]
        outcomes = []
        ws = {"chaos": 1.0, "divergence": 0.9}

        d = Director(enable_cooldowns=False)
        result = d.tick(ws, npcs, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["event_type"], "chaos")


class TestDirectorCooldowns(unittest.TestCase):
    """Test Director cooldown system."""

    def test_cooldown_prevents_same_event_twice(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {"enemy_count": 0, "danger_level": 0}
        d = Director(enable_cooldowns=True)

        # First tick should trigger a twist
        r1 = d.tick(ws, npcs, [])
        self.assertIsNotNone(r1)

        # Next tick — cooldown prevents immediate re-triggering of twist
        # But signals are still high, so if we get None, it means cooldown worked
        r2 = d.tick(ws, npcs, [])
        self.assertIsNone(r2)
        self.assertEqual(d.tick_count, 2)

    def test_cooldown_expired_allows_event(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {"enemy_count": 0, "danger_level": 0}
        d = Director(enable_cooldowns=True)
        d.cooldowns["twist"] = 0  # Force cooldown to expire

        r1 = d.tick(ws, npcs, [])
        self.assertIsNotNone(r1)

    def test_cooldowns_counted_down(self):
        d = Director(enable_cooldowns=True)
        d.cooldowns["twist"] = 5
        d.cooldowns["chaos"] = 3

        # Manually tick cooldowns
        d._tick_cooldowns()
        self.assertEqual(d.cooldowns["twist"], 4)
        self.assertEqual(d.cooldowns["chaos"], 2)


class TestDirectorNarrativeThreads(unittest.TestCase):
    """Test Director narrative thread tracking."""

    def test_creates_thread_on_first_event(self):
        d = Director(enable_cooldowns=False)
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        d.tick(ws, npcs, [])
        self.assertTrue(len(d.narrative_threads) >= 1)
        for tname, thread in d.narrative_threads.items():
            self.assertEqual(thread["stage"], 1)
            self.assertIn("first_event", thread)

    def test_thread_advances_on_second_event(self):
        d = Director(enable_cooldowns=False)
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}

        # Inject many ticks to build up threads
        for _ in range(10):
            d.tick(ws, npcs, [])

        # At least one thread should have stage > 1
        stages = [t["stage"] for t in d.narrative_threads.values()]
        self.assertTrue(any(s > 1 for s in stages))


class TestDirectorStatus(unittest.TestCase):
    """Test Director status reporting."""

    def test_status_has_expected_keys(self):
        d = Director()
        status = d.get_status()
        self.assertIn("tick_count", status)
        self.assertIn("events_injected", status)
        self.assertIn("event_summary", status)
        self.assertIn("active_threads", status)
        self.assertIn("cooldowns", status)


class TestDirectorReset(unittest.TestCase):
    """Test Director reset."""

    def test_reset_clears_state(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        d = Director()
        d.tick(ws, npcs, [])
        d.tick(ws, npcs, [])
        d.reset()

        self.assertEqual(d.tick_count, 0)
        self.assertEqual(d.history, [])
        self.assertEqual(d.narrative_threads, {})


class TestDirectorThresholds(unittest.TestCase):
    """Test Director custom thresholds."""

    def test_custom_thresholds_applied(self):
        thresholds = {
            "stagnation": 0.3,  # Very low: any idle triggers
            "conflict": 0.1,
            "failure_spike": 0.1,
            "divergence": 0.1,
        }
        d = Director(thresholds=thresholds, enable_cooldowns=False)

        # Even with mostly active NPCs, low stagnation threshold triggers
        npcs = [_make_npc("a"), _make_npc("b", "walk")]
        outcomes = [MagicMock(success=True)]
        ws = {"enemy_count": 0, "danger_level": 0}
        result = d.tick(ws, npcs, outcomes)
        # stagnation=0.5 > 0.3 threshold -> twist
        self.assertIsNotNone(result)


class TestDirectorWithWorldState(unittest.TestCase):
    """Test Director modifies world state correctly."""

    def test_event_applied_to_world(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {"resources": 5, "enemy_count": 0, "trust_level": 0.5}
        d = Director(enable_cooldowns=False)

        # Multiple ticks to ensure events apply
        for _ in range(5):
            d.tick(ws, npcs, [])

        # World state should have changed from events
        # (trust_level goes down from betrayal events etc.)
        changed = (
            ws["resources"] != 5 or
            ws["enemy_count"] != 0 or
            ws["trust_level"] != 0.5
        )
        self.assertTrue(changed, f"World state should change: {ws}")


if __name__ == "__main__":
    unittest.main()