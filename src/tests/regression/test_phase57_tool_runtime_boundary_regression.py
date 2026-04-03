import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.tool_runtime_boundary import ToolRuntimeGateway, ToolRuntimeRecorder
from app.rpg.validation.state_boundary_validator import StateBoundaryValidator


class _DummyRuntime:
    def __init__(self, provider="dummy-provider"):
        self.calls = []
        self.provider = provider

    def call(self, tool_name, payload):
        self.calls.append((tool_name, payload))
        return {"provider": self.provider, "tool_name": tool_name, "payload": payload}


class TestPhase57ToolRuntimeBoundaryRegression(unittest.TestCase):
    def test_recorded_outputs_are_snapshot_serializable(self):
        rec = ToolRuntimeRecorder()
        rec.record("search", {"q": "hello"}, {"result": 1}, {"npc": "guard"}, {"provider": "p1"})
        state = rec.serialize_state()

        rec2 = ToolRuntimeRecorder()
        rec2.deserialize_state(state)

        self.assertEqual(
            rec2.replay("search", {"q": "hello"}, {"npc": "guard"}, {"provider": "p1"}),
            {"result": 1},
        )

    def test_gateway_no_client_raises_error(self):
        gateway = ToolRuntimeGateway(
            runtime_client=None,
            recorder=ToolRuntimeRecorder(),
        )

        with self.assertRaises(RuntimeError):
            gateway.call("search", {"q": "hi"})

    def test_effect_policy_live_vs_replay_for_tools(self):
        live_manager = EffectManager(EffectPolicy(allow_tool_calls=True))
        replay_manager = EffectManager(EffectPolicy(allow_tool_calls=False))

        self.assertTrue(live_manager.is_allowed("tool_call"))
        self.assertFalse(replay_manager.is_allowed("tool_call"))

    def test_state_boundary_validator_tool_replay_safety(self):
        validator = StateBoundaryValidator()

        gateway = ToolRuntimeGateway(
            runtime_client=_DummyRuntime(),
            recorder=ToolRuntimeRecorder(),
            determinism=DeterminismConfig(use_recorded_tools=True, replay_mode=True),
            effect_manager=EffectManager(EffectPolicy(allow_tool_calls=False)),
        )

        result = validator.validate_tool_runtime_replay_safety(gateway)
        self.assertTrue(result["ok"])

    def test_config_sensitive_keying(self):
        rec = ToolRuntimeRecorder()
        rec.record("search", {"q": "x"}, {"r": 1}, {"npc": "guard"}, {"provider": "p1"})
        rec.record("search", {"q": "x"}, {"r": 2}, {"npc": "guard"}, {"provider": "p2"})

        self.assertEqual(
            rec.replay("search", {"q": "x"}, {"npc": "guard"}, {"provider": "p1"}),
            {"r": 1},
        )
        self.assertEqual(
            rec.replay("search", {"q": "x"}, {"npc": "guard"}, {"provider": "p2"}),
            {"r": 2},
        )

    def test_gateway_mode_switch_preserves_recorded_state(self):
        runtime = _DummyRuntime()
        recorder = ToolRuntimeRecorder()
        det = DeterminismConfig(record_tools=True)
        effects = EffectManager(EffectPolicy(allow_tool_calls=True))

        gateway = ToolRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        gateway.set_mode("live")
        out1 = gateway.call("search", {"q": "hello"}, context={})
        self.assertEqual(out1["tool_name"], "search")
        self.assertEqual(len(recorder.records), 1)

        gateway.set_mode("replay")
        out2 = gateway.call("search", {"q": "hello"}, context={})
        self.assertEqual(out2["tool_name"], "search")
        self.assertEqual(len(runtime.calls), 1)


if __name__ == "__main__":
    unittest.main()
