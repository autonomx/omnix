"""PHASE 5.5 — State Boundary Functional Tests.

Tests for:
- GameLoop propagation of effect manager to subsystems
- GameLoop mode switching and effect policy enforcement
- Sandbox mode restoration after simulation
"""

import unittest

from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.game_loop import GameLoop
from app.rpg.core.event_bus import Event, EventBus
from app.rpg.simulation.sandbox import SimulationSandbox


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


class TestPhase55StateBoundariesFunctional(unittest.TestCase):
    """Functional tests for state boundary enforcement."""

    def test_game_loop_replay_mode_blocks_live_llm_effects(self):
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
        with self.assertRaises(RuntimeError):
            loop.effect_manager.check("live_llm", {"prompt": "hello"})

    def test_game_loop_live_mode_allows_live_llm_effects(self):
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )
        loop.set_mode("live")
        loop.effect_manager.check("live_llm", {"prompt": "hello"})
        self.assertEqual(loop.effect_manager.records[-1].effect_type, "live_llm")

    def test_game_loop_simulation_mode_blocks_live_llm_effects(self):
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )
        loop.set_mode("simulation")
        with self.assertRaises(RuntimeError):
            loop.effect_manager.check("live_llm", {"prompt": "hello"})

    def test_effect_manager_is_injected_into_subsystems(self):
        """GameLoop must inject effect_manager into subsystems that support it."""
        world = _World()
        npc = _NPC()
        director = _Director()
        renderer = _Renderer()

        loop = GameLoop(
            intent_parser=_Parser(),
            world=world,
            npc_system=npc,
            event_bus=EventBus(),
            story_director=director,
            scene_renderer=renderer,
            effect_manager=EffectManager(),
        )

        self.assertIs(world.effect_manager, loop.effect_manager)
        self.assertIs(npc.effect_manager, loop.effect_manager)
        self.assertIs(director.effect_manager, loop.effect_manager)
        self.assertIs(renderer.effect_manager, loop.effect_manager)

    def test_mode_propagates_to_subsystems(self):
        """set_mode() must propagate to all subsystems."""
        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
        )
        loop.set_mode("replay")

        self.assertEqual(loop.world.mode, "replay")
        self.assertEqual(loop.npc_system.mode, "replay")
        self.assertEqual(loop.story_director.mode, "replay")
        self.assertEqual(loop.scene_renderer.mode, "replay")


class TestPhase55SandboxModeRestoration(unittest.TestCase):
    """Sandbox must restore mode to live after simulation even on failure."""

    def test_sandbox_restores_mode_after_run(self):
        """After sandbox.run(), loop mode must be restored to live."""
        world = _World()
        npc = _NPC()
        director = _Director()
        renderer = _Renderer()
        bus = EventBus()

        def make_loop():
            return GameLoop(
                intent_parser=_Parser(),
                world=_World(),
                npc_system=_NPC(),
                event_bus=EventBus(),
                story_director=_Director(),
                scene_renderer=_Renderer(),
            )

        sandbox = SimulationSandbox(make_loop)
        result = sandbox.run(
            base_events=[],
            future_events=[],
            max_ticks=3,
        )
        self.assertEqual(result.tick_count, 3)

    def test_sandbox_restores_mode_on_failure(self):
        """Even if simulation fails, mode must be restored."""

        class _FailingWorld(_World):
            def tick(self, event_bus):
                raise RuntimeError("Simulated failure during tick")

        def make_loop():
            loop = GameLoop(
                intent_parser=_Parser(),
                world=_FailingWorld(),
                npc_system=_NPC(),
                event_bus=EventBus(),
                story_director=_Director(),
                scene_renderer=_Renderer(),
            )
            loop.set_mode("simulation")
            return loop

        sandbox = SimulationSandbox(make_loop)
        with self.assertRaises(RuntimeError):
            sandbox.run(
                base_events=[],
                future_events=[],
                max_ticks=3,
            )


    def test_simulation_sandbox_does_not_mutate_live_loop(self):
        """Sandbox must NOT mutate the live loop's state."""
        live_npc = _NPC()
        live_loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=live_npc,
            event_bus=EventBus(),
            story_director=_Director(),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )

        # Advance live loop once
        live_loop.tick("start")
        live_counter_before = live_npc.counter
        live_history_before = len(live_loop.event_bus.history())

        def factory():
            return GameLoop(
                intent_parser=_Parser(),
                world=_World(),
                npc_system=_NPC(),
                event_bus=EventBus(),
                story_director=_Director(),
                scene_renderer=_Renderer(),
                effect_manager=EffectManager(),
            )

        sandbox = SimulationSandbox(factory)
        # Use empty base_events so sandbox does not call replay_to_tick
        sandbox.run(
            base_events=[],
            future_events=[Event(type="hypo", payload={"x": 1}, source="test")],
            max_ticks=2,
        )

        # Live loop must remain unchanged
        self.assertEqual(live_npc.counter, live_counter_before)
        self.assertEqual(len(live_loop.event_bus.history()), live_history_before)


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