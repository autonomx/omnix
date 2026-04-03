import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.tool_runtime_boundary import ToolRuntimeGateway, ToolRuntimeRecorder
from app.rpg.core.snapshot_manager import SnapshotManager


class _DummyRuntime:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, payload):
        self.calls.append((tool_name, payload))
        return {"tool": tool_name, "payload": payload, "ok": True}


class TestPhase57ToolRuntimeBoundary(unittest.TestCase):
    def test_live_tool_call_blocked_by_effect_policy(self):
        runtime = _DummyRuntime()
        recorder = ToolRuntimeRecorder()
        det = DeterminismConfig(record_tools=False, use_recorded_tools=False)
        effects = EffectManager(EffectPolicy(allow_tool_calls=False))

        gateway = ToolRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        with self.assertRaises(RuntimeError):
            gateway.call("search", {"q": "hello"}, context={"npc": "guard"})

        self.assertEqual(runtime.calls, [])

    def test_live_tool_call_allowed_and_recorded(self):
        runtime = _DummyRuntime()
        recorder = ToolRuntimeRecorder()
        det = DeterminismConfig(record_tools=True, use_recorded_tools=False)
        effects = EffectManager(EffectPolicy(allow_tool_calls=True))

        gateway = ToolRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        out = gateway.call("search", {"q": "hello"}, context={"npc": "guard"})
        self.assertTrue(out["ok"])
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(len(recorder.records), 1)

    def test_replay_uses_recorded_output_only(self):
        live_runtime = _DummyRuntime()
        recorder = ToolRuntimeRecorder()
        det_live = DeterminismConfig(record_tools=True, use_recorded_tools=False)
        effects_live = EffectManager(EffectPolicy(allow_tool_calls=True))

        gateway_live = ToolRuntimeGateway(
            runtime_client=live_runtime,
            recorder=recorder,
            determinism=det_live,
            effect_manager=effects_live,
        )
        gateway_live.call("search", {"q": "hello"}, context={"npc": "guard"})

        replay_runtime = _DummyRuntime()
        det_replay = DeterminismConfig(record_tools=False, use_recorded_tools=True, replay_mode=True)
        effects_replay = EffectManager(EffectPolicy(allow_tool_calls=False))

        gateway_replay = ToolRuntimeGateway(
            runtime_client=replay_runtime,
            recorder=recorder,
            determinism=det_replay,
            effect_manager=effects_replay,
        )

        out = gateway_replay.call("search", {"q": "hello"}, context={"npc": "guard"})
        self.assertTrue(out["ok"])
        self.assertEqual(replay_runtime.calls, [])

    def test_replay_missing_record_fails_hard(self):
        gateway = ToolRuntimeGateway(
            runtime_client=_DummyRuntime(),
            recorder=ToolRuntimeRecorder(),
            determinism=DeterminismConfig(use_recorded_tools=True, replay_mode=True),
            effect_manager=EffectManager(EffectPolicy(allow_tool_calls=False)),
        )

        with self.assertRaises(KeyError):
            gateway.call("search", {"q": "missing"}, context={"x": 1})

    def test_set_mode_switches_between_replay_and_live(self):
        runtime = _DummyRuntime()
        recorder = ToolRuntimeRecorder()
        det = DeterminismConfig()
        effects = EffectManager()

        gateway = ToolRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        gateway.set_mode("replay")
        self.assertTrue(det.replay_mode)
        self.assertTrue(det.use_recorded_tools)

        gateway.set_mode("live")
        self.assertFalse(det.replay_mode)
        self.assertFalse(det.use_recorded_tools)

    def test_snapshot_roundtrip_tool_runtime_state(self):
        """SnapshotManager should save and restore tool runtime recorder state."""
        class _Loop:
            def __init__(self):
                self.tool_runtime_recorder = ToolRuntimeRecorder()

        loop1 = _Loop()
        loop1.tool_runtime_recorder.record(
            "search",
            {"q": "hello"},
            {"result": 1},
            {"npc": "guard"},
            {"provider": "dummy"},
        )

        manager = SnapshotManager()
        manager.save_snapshot(3, loop1)

        loop2 = _Loop()
        loaded = manager.load_snapshot(3, loop2)

        self.assertTrue(loaded)
        self.assertEqual(
            loop2.tool_runtime_recorder.replay(
                "search",
                {"q": "hello"},
                {"npc": "guard"},
                {"provider": "dummy"},
            ),
            {"result": 1},
        )


if __name__ == "__main__":
    unittest.main()
