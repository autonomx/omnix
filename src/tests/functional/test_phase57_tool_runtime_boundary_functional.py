import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager
from app.rpg.core.event_bus import EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.core.tool_runtime_boundary import ToolRuntimeGateway, ToolRuntimeRecorder


class _Parser:
    def parse(self, s):
        return {"text": s}


class _World:
    def tick(self, event_bus):
        pass
    def set_mode(self, mode):
        self.mode = mode
    def set_effect_manager(self, em):
        self.effect_manager = em
    def set_tool_runtime_recorder(self, recorder):
        self.tool_runtime_recorder = recorder


class _NPC:
    def update(self, intent, event_bus):
        pass
    def set_mode(self, mode):
        self.mode = mode
    def set_effect_manager(self, em):
        self.effect_manager = em
    def set_tool_runtime_recorder(self, recorder):
        self.tool_runtime_recorder = recorder


class _Renderer:
    def render(self, narrative):
        return narrative
    def set_mode(self, mode):
        self.mode = mode
    def set_effect_manager(self, em):
        self.effect_manager = em
    def set_tool_runtime_recorder(self, recorder):
        self.tool_runtime_recorder = recorder


class _DummyRuntime:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, payload):
        self.calls.append((tool_name, payload))
        return {"ok": True, "tool_name": tool_name, "payload": payload}


class _Director:
    def __init__(self, gateway):
        self.gateway = gateway

    def process(self, events, intent, event_bus):
        result = self.gateway.call("lookup", {"intent": intent["text"]}, context={"phase": "director"})
        return {"tool_result": result}

    def set_mode(self, mode):
        self.mode = mode
        if hasattr(self.gateway, "set_mode"):
            self.gateway.set_mode(mode)

    def set_effect_manager(self, em):
        self.effect_manager = em
        if hasattr(self.gateway, "set_effect_manager"):
            self.gateway.set_effect_manager(em)

    def set_tool_runtime_recorder(self, recorder):
        self.tool_runtime_recorder = recorder
        if hasattr(self.gateway, "set_tool_runtime_recorder"):
            self.gateway.set_tool_runtime_recorder(recorder)


class TestPhase57ToolRuntimeBoundaryFunctional(unittest.TestCase):
    def test_replay_blocks_fresh_tool_calls_and_uses_recorded(self):
        recorder = ToolRuntimeRecorder()
        runtime = _DummyRuntime()

        gateway = ToolRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=DeterminismConfig(record_tools=True, use_recorded_tools=False),
            effect_manager=None,
        )

        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(gateway),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
            tool_runtime_recorder=recorder,
        )

        loop.set_tool_runtime_recorder(recorder)
        loop.set_mode("live")

        out1 = loop.story_director.process([], {"text": "wait"}, loop.event_bus)
        self.assertTrue(out1["tool_result"]["ok"])
        self.assertEqual(len(runtime.calls), 1)

        loop.set_mode("replay")
        out2 = loop.story_director.process([], {"text": "wait"}, loop.event_bus)

        self.assertTrue(out2["tool_result"]["ok"])
        self.assertEqual(len(runtime.calls), 1)

    def test_tool_runtime_recorder_serialization_roundtrip(self):
        recorder = ToolRuntimeRecorder()
        recorder.record("search", {"q": "a"}, {"ok": True}, {"ctx": "x"}, {"provider": "dummy"})
        recorder.record("fetch", {"id": 2}, {"ok": True}, {"ctx": "y"}, {"provider": "dummy"})

        state = recorder.serialize_state()
        self.assertEqual(len(state["records"]), 2)

        restored = ToolRuntimeRecorder()
        restored.deserialize_state(state)

        self.assertEqual(
            restored.replay("search", {"q": "a"}, {"ctx": "x"}, {"provider": "dummy"}),
            {"ok": True},
        )

    def test_replay_missing_tool_record_fails_hard(self):
        """Replay mode must fail hard when a tool/runtime output is missing."""
        gateway = ToolRuntimeGateway(
            runtime_client=_DummyRuntime(),
            recorder=ToolRuntimeRecorder(),
            determinism=DeterminismConfig(
                record_tools=False,
                use_recorded_tools=True,
                replay_mode=True,
            ),
            effect_manager=EffectManager(),
        )

        with self.assertRaises(KeyError):
            gateway.call("lookup", {"intent": "unknown"}, context={"phase": "director"})


if __name__ == "__main__":
    unittest.main()
