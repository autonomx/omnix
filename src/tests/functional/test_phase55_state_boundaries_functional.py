"""PHASE 5.5 — State Boundary Functional Tests.

Tests for:
- GameLoop propagation of effect manager to subsystems
- GameLoop mode switching and effect policy enforcement
- Sandbox mode restoration after simulation
"""

import unittest

from app.apps.rpg.foundation.core.effects import EffectManager, EffectPolicy
from app.apps.rpg.foundation.core.event_bus import Event


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
        self.counter = 0

    def set_mode(self, mode):
        self.mode = mode

    def set_effect_manager(self, effect_manager):
        self.effect_manager = effect_manager

    def update(self, intent, event_bus):
        self.counter += 1
        event_bus.emit(Event(type="npc_tick", payload={"counter": self.counter}, source="npc"))
        return None

    def serialize_state(self):
        return {"counter": self.counter}

    def deserialize_state(self, state):
        self.counter = state["counter"]


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


class TestPhase55EffectPolicyIntegration(unittest.TestCase):
    """Integration tests for effect policy enforcement."""

    def test_is_allowed_allows_branching_instead_of_exception(self):
        """Systems should use is_allowed() for clean branching."""
        mgr = EffectManager(EffectPolicy(allow_live_llm=False))

        # Branch cleanly instead of try/except
        if mgr.is_allowed("live_llm"):
            mgr.check("live_llm", {"prompt": "hello"})

        # Nothing recorded because we never called check
        self.assertEqual(len(mgr.records), 0)

    def test_is_allowed_check_consistency(self):
        """is_allowed() should return same result as check() policy."""
        mgr = EffectManager(EffectPolicy(
            allow_logs=True,
            allow_network=False,
            allow_live_llm=True,
        ))

        self.assertTrue(mgr.is_allowed("log"))
        self.assertFalse(mgr.is_allowed("network"))
        self.assertTrue(mgr.is_allowed("live_llm"))

        # check should match
        mgr.check("log", {})
        mgr.check("live_llm", {})
        with self.assertRaises(RuntimeError):
            mgr.check("network", {})


if __name__ == "__main__":
    unittest.main()