"""PHASE 5.5 — State Boundary Regression Tests.

Tests for:
- EffectPolicy defaults remain replay-safe
- EffectManager serialization roundtrip consistency
- Blocked effects are recorded before failure
- State isolation between managers (no leakage)
- No regression in policy enforcement
"""

import unittest

from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.event_bus import EventBus
from app.rpg.core.game_loop import GameLoop


class _Parser:
    def parse(self, s):
        return {"text": s}


class _World:
    def __init__(self):
        self.mode = "live"
        self.effect_manager = None

    def set_mode(self, mode):
        self.mode = mode

    def set_effect_manager(self, effect_manager):
        self.effect_manager = effect_manager

    def tick(self, event_bus):
        return None


class _NPC:
    def __init__(self):
        self.mode = "live"
        self.effect_manager = None

    def set_mode(self, mode):
        self.mode = mode

    def set_effect_manager(self, effect_manager):
        self.effect_manager = effect_manager

    def update(self, intent, event_bus):
        return None


class _Director:
    def __init__(self):
        self.mode = "live"
        self.effect_manager = None

    def set_mode(self, mode):
        self.mode = mode

    def set_effect_manager(self, effect_manager):
        self.effect_manager = effect_manager

    def process(self, events, intent, event_bus):
        return {"events": [e.type for e in events]}


class _Renderer:
    def __init__(self):
        self.mode = "live"
        self.effect_manager = None

    def set_mode(self, mode):
        self.mode = mode

    def set_effect_manager(self, effect_manager):
        self.effect_manager = effect_manager

    def render(self, narrative):
        return narrative


class TestPhase55StateBoundariesRegression(unittest.TestCase):
    """Regression tests to prevent future breakage of state boundaries."""

    def test_effect_policy_defaults_are_replay_safe(self):
        """Default policy must NOT allow external effects."""
        policy = EffectPolicy()
        self.assertFalse(policy.allow_network)
        self.assertFalse(policy.allow_disk_write)
        self.assertFalse(policy.allow_live_llm)
        self.assertFalse(policy.allow_tool_calls)
        # Logs and metrics should be allowed (for debugging)
        self.assertTrue(policy.allow_logs)
        self.assertTrue(policy.allow_metrics)

    def test_effect_manager_serialization_roundtrip(self):
        """Serialized state must survive roundtrip unchanged."""
        mgr = EffectManager()
        state = mgr.serialize_state()
        mgr2 = EffectManager()
        mgr2.deserialize_state(state)
        self.assertEqual(mgr2.serialize_state(), state)

    def test_blocked_effect_is_recorded_before_failure(self):
        """Even blocked effects must be recorded for debugging."""
        mgr = EffectManager()
        with self.assertRaises(RuntimeError):
            mgr.check("network", {"url": "x"})
        self.assertEqual(len(mgr.records), 1)
        self.assertEqual(mgr.records[0].effect_type, "network")

    def test_effect_policy_custom_allows_network(self):
        mgr = EffectManager(EffectPolicy(allow_network=True))
        mgr.check("network", {"url": "https://api.example.com"})
        self.assertEqual(mgr.records[-1].effect_type, "network")

    def test_effect_manager_state_isolation(self):
        """Two managers must not share state."""
        mgr1 = EffectManager(EffectPolicy(allow_live_llm=True))
        mgr2 = EffectManager(EffectPolicy(allow_live_llm=False))
        mgr1.check("live_llm", {"prompt": "test"})
        with self.assertRaises(RuntimeError):
            mgr2.check("live_llm", {"prompt": "test"})

    def test_effect_policy_switch_does_not_leak_state(self):
        """Switching policies must not carry over records from old manager."""
        mgr = EffectManager(EffectPolicy(allow_live_llm=True))
        mgr.check("live_llm", {"prompt": "first"})
        self.assertEqual(len(mgr.records), 1)

        # New manager with different policy
        mgr2 = EffectManager(EffectPolicy(allow_live_llm=False))
        self.assertEqual(len(mgr2.records), 0)

    def test_gameloop_set_mode_does_not_corrupt_state(self):
        """Switching modes should not lose effect_manager state."""
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )

        # Record some effects in live mode
        loop.effect_manager.check("log", {"msg": "before"})
        self.assertEqual(len(loop.effect_manager.records), 1)

        # Switch to replay mode
        loop.set_mode("replay")

        # Previous records should still exist
        self.assertEqual(len(loop.effect_manager.records), 1)
        self.assertEqual(loop.effect_manager.records[0].payload, {"msg": "before"})

    def test_is_allowed_and_check_consistency(self):
        """is_allowed() must match what check() would enforce."""
        mgr = EffectManager(EffectPolicy(
            allow_logs=True,
            allow_network=False,
            allow_live_llm=True,
            allow_tool_calls=False,
        ))

        # is_allowed should agree with check
        for effect_type, expected in [
            ("log", True),
            ("metric", True),
            ("network", False),
            ("disk_write", False),
            ("live_llm", True),
            ("tool_call", False),
        ]:
            self.assertEqual(mgr.is_allowed(effect_type), expected, f"is_allowed({effect_type})")


class TestPhase55NoStateLeak(unittest.TestCase):
    """State leakage from simulation back to live loop must not occur."""

    def test_simulation_mode_blocks_network(self):
        """Simulation mode must block network effects."""
        mgr = EffectManager()
        mgr.set_policy(EffectPolicy(
            allow_logs=True,
            allow_metrics=True,
            allow_network=False,
            allow_disk_write=False,
            allow_live_llm=False,
            allow_tool_calls=False,
        ))
        with self.assertRaises(RuntimeError):
            mgr.check("network", {"url": "https://api.example.com"})

    def test_gameloop_default_mode_is_live(self):
        """New GameLoop must default to live mode."""
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
        )
        self.assertEqual(loop.mode, "live")

    def test_replay_mode_blocks_all_external_effects(self):
        """Replay mode must block ALL external effects."""
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )
        loop.set_mode("replay")

        for effect_type in ("network", "disk_write", "live_llm", "tool_call"):
            with self.subTest(effect_type=effect_type):
                with self.assertRaises(RuntimeError):
                    loop.effect_manager.check(effect_type, {"payload": "test"})


if __name__ == "__main__":
    unittest.main()