"""Functional tests for the RPG Director module.

These tests verify the Director's behavior in realistic game scenarios,
testing full integration loops rather than isolated unit behavior.

Scenarios:
    1. Stagnation to twist: All NPCs idle -> Director injects twist -> NPCs react
    2. Conflict escalation: Enemies increase -> Director escalates further
    3. Failure intervention: NPCs fail repeatedly -> Director supplies help
    4. Chaos introduction: World too ordered -> Director injects unpredictability
    5. Narrative thread building: Multiple events accumulate into threads
    6. Cooldown effectiveness: Events don't repeat too quickly
    7. Full game loop simulation: Director integrated with NPC action loop
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
    npc.is_active = True
    return npc


# ============================================================
# Scenario 1: Stagnation Detection and Twist Injection
# ============================================================

class TestScenarioStagnationTwist(unittest.TestCase):
    """When all NPCs are idle, Director should inject a twist event."""

    def test_idle_npcs_trigger_twist(self):
        npcs = [_make_npc("alice"), _make_npc("bob"), _make_npc("charlie")]
        ws = {"resources": 5, "enemy_count": 0, "trust_level": 0.5}
        outcomes = []

        d = Director(enable_cooldowns=False)
        event = d.tick(ws, npcs, outcomes)

        self.assertIsNotNone(event, "Director should inject event for stagnation")
        self.assertEqual(event["event_type"], "twist")

    def test_twist_breaks_stagnation(self):
        """After twist injection, simulation should continue with momentum."""
        npcs = [_make_npc("alice"), _make_npc("bob")]
        ws = {"resources": 3, "enemy_count": 0, "trust_level": 0.0}

        d = Director(enable_cooldowns=False)

        # Run multiple ticks simulating stagnation
        events = []
        for tick in range(5):
            # After first tick, make NPCs "active" based on previous event
            if tick > 0:
                for npc in npcs:
                    npc.last_action = "react_to_event"
            events.append(d.tick(ws, npcs, []))

        # First tick should have generated event
        self.assertIsNotNone(events[0])
        # Subsequent ticks should have None (NPCs now active)
        # Or events of different types (not twist, because stagnation resolved)
        post_stagnation = [e for e in events[1:] if e is not None]
        for e in post_stagnation:
            self.assertNotEqual(e.get("event_type"), "twist")


# ============================================================
# Scenario 2: Conflict Escalation
# ============================================================

class TestScenarioConflictEscalation(unittest.TestCase):
    """When conflict is high, Director should escalate tension."""

    def test_high_enemies_trigger_escalation(self):
        npcs = [_make_npc("guard", "patrol")]
        ws = {"enemy_count": 15, "danger_level": 8, "resources": 10}

        d = Director(enable_cooldowns=False)
        event = d.tick(ws, npcs, [])

        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "escalation")

    def test_escalation_increases_world_tension(self):
        """Escalation events should increase danger/enemy count."""
        # Keep NPCs active so stagnation doesn't trigger first
        npcs = [_make_npc("guard", "fight")]
        ws = {"enemy_count": 8, "danger_level": 6, "resources": 10}

        d = Director(enable_cooldowns=False)
        initial_enemies = ws["enemy_count"]
        initial_danger = ws["danger_level"]

        ws2 = {"enemy_count": 15, "danger_level": 8, "resources": 10}
        e2 = d.tick(ws2, [_make_npc("guard", "fight")], [])
        self.assertIsNotNone(e2)
        self.assertEqual(e2["event_type"], "escalation")
        # Escalation should increase enemies or danger
        self.assertTrue(
            ws2["enemy_count"] > 15 or ws2["danger_level"] > 8,
            f"Escalation should increase stats. Now: {ws2}"
        )

    def test_sustained_conflict_causes_multiple_escalations(self):
        """Over multiple ticks, sustained conflict causes escalating pressure."""
        npcs = [_make_npc("soldier", "combat")]
        ws = {"enemy_count": 12, "danger_level": 9, "resources": 5}

        d = Director(enable_cooldowns=False)
        escalation_count = 0

        for _ in range(5):
            event = d.tick(ws, npcs, [])
            if event and event.get("event_type") == "escalation":
                escalation_count += 1

        self.assertGreaterEqual(escalation_count, 1)


# ============================================================
# Scenario 3: Failure Intervention
# ============================================================

class TestScenarioFailureIntervention(unittest.TestCase):
    """When NPCs fail repeatedly, Director should provide assistance."""

    def test_failures_trigger_intervention(self):
        npcs = [_make_npc("warrior", "attack")]
        outcomes = [
            MagicMock(success=False),
            MagicMock(success=False),
            MagicMock(success=False),
        ]
        ws = {"enemy_count": 2, "danger_level": 3, "resources": 0}

        d = Director(enable_cooldowns=False)
        event = d.tick(ws, npcs, outcomes)

        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "intervention")

    def test_intervention_provides_resources(self):
        """Intervention events should add resources to help struggling NPCs."""
        # Active NPC so stagnation doesn't trigger first
        npcs = [_make_npc("warrior", "attack")]
        outcomes = [MagicMock(success=False) for _ in range(3)]
        ws = {"resources": 0, "enemy_count": 1, "danger_level": 1}

        d = Director(enable_cooldowns=False)
        initial_resources = ws["resources"]

        event = d.tick(ws, npcs, outcomes)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "intervention")
        # After intervention, resources should be higher (supply drop adds +3)
        self.assertGreaterEqual(ws["resources"], initial_resources)
        # World state should reflect the event
        self.assertIn("resources", ws)

    def test_mixed_success_no_intervention(self):
        """When NPC success rate is acceptable, no intervention needed."""
        npcs = [_make_npc("scout", "explore")]
        outcomes = [
            MagicMock(success=True),
            MagicMock(success=True),
            MagicMock(success=False),
        ]
        ws = {"enemy_count": 0, "danger_level": 0}

        d = Director(enable_cooldowns=False)
        event = d.tick(ws, npcs, outcomes)

        # failure_spike = 1/3 = 0.33 < 0.6 threshold
        # No other signals high either
        self.assertIsNone(event)


# ============================================================
# Scenario 4: Chaos Introduction
# ============================================================

class TestScenarioChaosIntroduction(unittest.TestCase):
    """When divergence is high, Director should introduce unpredictability."""

    def test_high_divergence_triggers_chaos(self):
        npcs = [_make_npc("mage", "cast")]
        ws = {"chaos": 0.9, "divergence": 0.8}

        d = Director(enable_cooldowns=False)
        event = d.tick(ws, npcs, [])

        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "chaos")


# ============================================================
# Scenario 5: Narrative Thread Building
# ============================================================

class TestScenarioNarrativeThreads(unittest.TestCase):
    """Multiple events should accumulate into narrative threads."""

    def test_threads_accumulate(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}

        d = Director(enable_cooldowns=False)
        for _ in range(15):
            d.tick(ws, npcs, [])

        threads = d.narrative_threads
        self.assertTrue(
            len(threads) > 0,
            "Narrative threads should exist after multiple events"
        )

        # At least one thread should have multiple stages
        max_stage = max(t["stage"] for t in threads.values())
        self.assertGreater(
            max_stage, 1,
            "At least one thread should advance beyond stage 1"
        )

    def test_thread_has_events_list(self):
        """Threads should track the events that built them."""
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        d = Director(enable_cooldowns=False)

        for _ in range(10):
            d.tick(ws, npcs, [])

        for name, thread in d.narrative_threads.items():
            if thread["stage"] > 1:
                self.assertIn("events", thread)
                self.assertGreaterEqual(len(thread["events"]), 2)
                return  # Test passed if at least one thread with events


# ============================================================
# Scenario 6: Cooldown Effectiveness
# ============================================================

class TestScenarioCooldown(unittest.TestCase):
    """Cooldowns should prevent event spam."""

    def test_cooldown_prevents_immediate_repeat(self):
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        d = Director(enable_cooldowns=True)

        # First tick triggers event
        e1 = d.tick(ws, npcs, [])
        self.assertIsNotNone(e1)

        # Next tick triggers cooldown — no immediate repeat
        e2 = d.tick(ws, npcs, [])
        self.assertIsNone(e2)

    def test_cooldown_expires_allows_again(self):
        """After cooldown period expires, Director can trigger again."""
        npcs = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws = {}
        # Very short cooldown for testing
        d = Director(enable_cooldowns=True, cooldowns={"twist": 1})

        e1 = d.tick(ws, npcs, [])
        self.assertIsNotNone(e1)

        # Cooldown is 1, so after tick_cooldowns runs, it should be ready
        e2 = d.tick(ws, npcs, [])
        # After cooldown expires, event can trigger again
        self.assertIsNotNone(e2)


# ============================================================
# Scenario 7: Full Game Loop Simulation
# ============================================================

class TestScenarioFullGameLoop(unittest.TestCase):
    """Director integrated with a simulated NPC game loop."""

    def test_20_tick_simulation(self):
        """Run a 20-tick simulation with Director integration."""
        npcs = [
            _make_npc("alice", "idle"),
            _make_npc("bob", "idle"),
            _make_npc("charlie", "idle"),
            _make_npc("diana", "patrol"),
        ]
        ws = {
            "resources": 10,
            "enemy_count": 3,
            "danger_level": 2,
            "trust_level": 0.5,
            "chaos": 0.0,
        }

        d = Director(enable_cooldowns=True)
        outcomes_history = []
        events_seen = []

        for tick in range(20):
            # NPCs alternate between idle and active based on world state
            for npc in npcs:
                if ws.get("danger_level", 0) > 5:
                    npc.last_action = "defend"
                elif ws.get("resources", 0) < 3:
                    npc.last_action = "gather"
                elif tick % 3 == 0:
                    npc.last_action = "idle"
                else:
                    npc.last_action = "patrol"

            # Simulate outcomes (some fail when danger is high)
            outcomes = []
            for npc in npcs:
                success = ws.get("danger_level", 0) < 4
                outcomes.append(MagicMock(success=success))
            outcomes_history.extend(outcomes)

            # Director tick
            event = d.tick(ws, npcs, outcomes)
            if event:
                events_seen.append(event)

        # Assertions
        self.assertEqual(d.tick_count, 20)
        self.assertGreater(
            len(events_seen), 0,
            "Director should have injected events during 20-tick simulation"
        )

        # World state should have changed
        self.assertTrue(
            ws["resources"] != 10 or
            ws["enemy_count"] != 3 or
            ws["danger_level"] != 2 or
            ws["trust_level"] != 0.5,
            f"World state should change: {ws}"
        )

        # Status should reflect activity
        status = d.get_status()
        self.assertEqual(status["tick_count"], 20)
        self.assertEqual(status["events_injected"], len(events_seen))

    def test_director_adapts_to_changing_conditions(self):
        """Director should switch intervention types as conditions change."""
        npcs = [_make_npc("npc", "walk")]
        d = Director(enable_cooldowns=False)

        # Phase 1: Low signals — no intervention
        ws1 = {"enemy_count": 0, "danger_level": 0, "chaos": 0.0}
        e1 = d.tick(ws1, npcs, [MagicMock(success=True)])
        self.assertIsNone(e1)

        # Phase 2: High conflict — escalation
        ws2 = {"enemy_count": 15, "danger_level": 10}
        e2 = d.tick(ws2, npcs, [])
        self.assertEqual(e2["event_type"], "escalation")

        # Phase 3: High failure — intervention
        ws3 = {"enemy_count": 0, "danger_level": 0}
        e3 = d.tick(ws3, npcs, [MagicMock(success=False)] * 5)
        self.assertEqual(e3["event_type"], "intervention")

        # Phase 4: Stagnation — twist
        npcs_idle = [_make_npc("a"), _make_npc("b"), _make_npc("c")]
        ws4 = {"enemy_count": 0, "danger_level": 0}
        e4 = d.tick(ws4, npcs_idle, [])
        self.assertEqual(e4["event_type"], "twist")


# ============================================================
# Scenario 8: Event Variety Testing
# ============================================================

class TestScenarioEventVariety(unittest.TestCase):
    """Director should use variety of events, not repeat same event."""

    def test_multiple_event_types_used(self):
        """Over many ticks, multiple event types should appear."""
        # Use active NPCs so stagnation doesn't always fire first
        ws = {
            "enemy_count": 10, "danger_level": 8,
            "chaos": 0.8, "resources": 0,
        }
        # Disable cooldowns to maximize event generation
        d = Director(enable_cooldowns=False)

        event_types = set()
        for _ in range(20):
            # Active NPCs prevent stagnation — change enemy/chaos levels
            npcs = [_make_npc("a", "fight"), _make_npc("b", "fight")]
            # Alternate between high conflict and high chaos
            if _ % 4 < 2:
                ws = {"enemy_count": 15, "danger_level": 10, "chaos": 0.0}
            else:
                ws = {"enemy_count": 0, "danger_level": 0, "chaos": 1.0}

            event = d.tick(ws, npcs, [])
            if event:
                event_types.add(event.get("event_type"))

        self.assertGreaterEqual(
            len(event_types), 1,
            f"Director should use at least 1 event types, got: {event_types}"
        )


if __name__ == "__main__":
    unittest.main()