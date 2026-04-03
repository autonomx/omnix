import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.host_runtime_boundary import HostRuntimeGateway, HostRuntimeRecorder
from app.rpg.core.snapshot_manager import SnapshotManager


class _DummyHostRuntime:
    """Mock host/runtime provider for testing."""

    def __init__(self):
        self.calls = []

    def call(self, op_name, payload):
        self.calls.append((op_name, payload))
        return {"op": op_name, "payload": payload, "ok": True}

    def get_env(self, key):
        self.calls.append(("get_env", key))
        return {"env": key, "value": f"mock_{key}"}

    def list_dir(self, path):
        self.calls.append(("list_dir", path))
        return {"dir": path, "files": ["file1.txt", "file2.txt"]}

    def wall_time(self, _):
        self.calls.append(("wall_time", None))
        return {"time": 1234567890.0}

    def run_process(self, cmd):
        self.calls.append(("run_process", cmd))
        return {"cmd": cmd, "stdout": "mock output", "returncode": 0}


class TestPhase58HostRuntimeBoundary(unittest.TestCase):
    """Unit tests for Phase 5.8 — Host/Process Boundary."""

    def test_live_host_call_blocked_by_effect_policy(self):
        """Test that host/runtime calls are blocked by effect policy."""
        runtime = _DummyHostRuntime()
        recorder = HostRuntimeRecorder()
        det = DeterminismConfig(record_host=False, use_recorded_host=False)
        effects = EffectManager(EffectPolicy(
            allow_env_read=False,
            allow_filesystem_read=False,
            allow_wall_clock=False,
            allow_process_spawn=False,
        ))

        gateway = HostRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        # env_read is blocked
        with self.assertRaises(RuntimeError):
            gateway.call("get_env", {"key": "PATH"}, context={"npc": "guard"})

        self.assertEqual(runtime.calls, [])

    def test_live_host_call_allowed_and_recorded(self):
        """Test that host/runtime calls are allowed and recorded when policy permits."""
        runtime = _DummyHostRuntime()
        recorder = HostRuntimeRecorder()
        det = DeterminismConfig(record_host=True, use_recorded_host=False)
        effects = EffectManager(EffectPolicy(
            allow_env_read=True,
            allow_filesystem_read=True,
            allow_wall_clock=True,
            allow_process_spawn=True,
        ))

        gateway = HostRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        out = gateway.call("get_env", {"key": "PATH"}, context={"npc": "guard"})
        self.assertTrue(out["ok"])
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(len(recorder.records), 1)

    def test_replay_uses_recorded_output_only(self):
        """Test that replay uses recorded host/runtime output."""
        # Record phase
        live_runtime = _DummyHostRuntime()
        recorder = HostRuntimeRecorder()
        det_live = DeterminismConfig(record_host=True, use_recorded_host=False)
        effects_live = EffectManager(EffectPolicy(
            allow_env_read=True,
            allow_filesystem_read=True,
            allow_wall_clock=True,
            allow_process_spawn=True,
        ))

        gateway_live = HostRuntimeGateway(
            runtime_client=live_runtime,
            recorder=recorder,
            determinism=det_live,
            effect_manager=effects_live,
        )
        gateway_live.call("get_env", {"key": "PATH"}, context={"npc": "guard"})

        # Replay phase
        replay_runtime = _DummyHostRuntime()
        det_replay = DeterminismConfig(record_host=False, use_recorded_host=True, replay_mode=True)
        effects_replay = EffectManager(EffectPolicy(
            allow_env_read=False,
            allow_filesystem_read=False,
            allow_wall_clock=False,
            allow_process_spawn=False,
        ))

        gateway_replay = HostRuntimeGateway(
            runtime_client=replay_runtime,
            recorder=recorder,
            determinism=det_replay,
            effect_manager=effects_replay,
        )

        out = gateway_replay.call("get_env", {"key": "PATH"}, context={"npc": "guard"})
        self.assertTrue(out["ok"])
        # Replay should NOT call the real runtime
        self.assertEqual(replay_runtime.calls, [])

    def test_replay_missing_record_fails_hard(self):
        """Test that replay fails hard when no recorded data exists."""
        gateway = HostRuntimeGateway(
            runtime_client=_DummyHostRuntime(),
            recorder=HostRuntimeRecorder(),
            determinism=DeterminismConfig(use_recorded_host=True, replay_mode=True),
            effect_manager=EffectManager(EffectPolicy(
                allow_env_read=False,
                allow_filesystem_read=False,
                allow_wall_clock=False,
                allow_process_spawn=False,
            )),
        )

        with self.assertRaises(KeyError):
            gateway.call("get_env", {"key": "HOME"}, context={"x": 1})

    def test_set_mode_switches_between_replay_and_live(self):
        """Test set_mode switches between replay and live."""
        runtime = _DummyHostRuntime()
        recorder = HostRuntimeRecorder()
        det = DeterminismConfig()
        effects = EffectManager()

        gateway = HostRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        # Default — live
        self.assertFalse(gateway.determinism.replay_mode)
        self.assertFalse(gateway.determinism.use_recorded_host)

        # Switch to replay
        gateway.set_mode("replay")
        self.assertTrue(gateway.determinism.replay_mode)
        self.assertTrue(gateway.determinism.use_recorded_host)

        # Switch back to live
        gateway.set_mode("live")
        self.assertFalse(gateway.determinism.replay_mode)
        self.assertFalse(gateway.determinism.use_recorded_host)

    def test_serialization_roundtrip(self):
        """Test HostRuntimeRecorder serialization roundtrip."""
        recorder = HostRuntimeRecorder()
        recorder.record("get_env", {"key": "PATH"}, {"value": "/usr/bin"}, context={"npc": "test"})
        recorder.record("wall_time", None, {"time": 1234567890.0})

        state = recorder.serialize_state()
        new_recorder = HostRuntimeRecorder()
        new_recorder.deserialize_state(state)

        self.assertEqual(len(new_recorder.records), 2)
        replay_result = new_recorder.replay("get_env", {"key": "PATH"}, context={"npc": "test"})
        self.assertEqual(replay_result, {"value": "/usr/bin"})

    def test_gateway_without_client_raises(self):
        """Test that HostRuntimeGateway without runtime client raises."""
        gateway = HostRuntimeGateway(
            runtime_client=None,
            recorder=HostRuntimeRecorder(),
            determinism=DeterminismConfig(),
        )

        with self.assertRaises(RuntimeError):
            gateway.call("get_env", {"key": "PATH"})

    def test_effect_policy_serialization_roundtrip(self):
        """Test EffectPolicy serialization roundtrip with host policies."""
        effects = EffectManager(EffectPolicy(
            allow_env_read=True,
            allow_filesystem_read=True,
            allow_wall_clock=False,
            allow_process_spawn=False,
        ))

        state = effects.serialize_state()
        new_effects = EffectManager()
        new_effects.deserialize_state(state)

        self.assertTrue(new_effects.policy.allow_env_read)
        self.assertTrue(new_effects.policy.allow_filesystem_read)
        self.assertFalse(new_effects.policy.allow_wall_clock)
        self.assertFalse(new_effects.policy.allow_process_spawn)

    def test_snapshot_manager_integration(self):
        """Test that host runtime recorder integrates with SnapshotManager."""
        recorder = HostRuntimeRecorder()
        recorder.record("get_env", {"key": "PATH"}, {"value": "/usr/bin"})
        recorder.record("list_dir", {"path": "/tmp"}, {"files": ["a.txt"]})

        # Serialize state for snapshot
        state = recorder.serialize_state()
        self.assertEqual(len(state["records"]), 2)

    def test_set_host_runtime_recorder(self):
        """Test set_host_runtime_recorder updates the recorder."""
        runtime = _DummyHostRuntime()
        recorder1 = HostRuntimeRecorder()
        det = DeterminismConfig(record_host=True)

        gateway = HostRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder1,
            determinism=det,
        )

        # Make a call using recorder1
        gateway.call("get_env", {"key": "PATH"})
        self.assertEqual(len(recorder1.records), 1)

        # Switch to recorder2
        recorder2 = HostRuntimeRecorder()
        gateway.set_host_runtime_recorder(recorder2)

        # Make a call - should use recorder2
        gateway.call("get_env", {"key": "HOME"})
        self.assertEqual(len(recorder1.records), 1)
        self.assertEqual(len(recorder2.records), 1)

    def test_op_to_effect_mapping(self):
        """Test that DeterministicHostRuntimeClient maps operations to effects correctly."""
        from app.rpg.core.host_runtime_boundary import DeterministicHostRuntimeClient

        recorder = HostRuntimeRecorder()
        det = DeterminismConfig()

        client = DeterministicHostRuntimeClient(
            inner_client=_DummyHostRuntime(),
            recorder=recorder,
            determinism=det,
        )

        # Check mapping correctness
        self.assertEqual(client.OP_TO_EFFECT["get_env"], "env_read")
        self.assertEqual(client.OP_TO_EFFECT["list_dir"], "filesystem_read")
        self.assertEqual(client.OP_TO_EFFECT["wall_time"], "wall_clock")
        self.assertEqual(client.OP_TO_EFFECT["run_process"], "process_spawn")

    def test_is_allowed_effect_type(self):
        """Test EffectManager.is_allowed for host effect types."""
        effects = EffectManager(EffectPolicy(
            allow_env_read=True,
            allow_filesystem_read=False,
            allow_wall_clock=True,
            allow_process_spawn=False,
        ))

        self.assertTrue(effects.is_allowed("env_read"))
        self.assertFalse(effects.is_allowed("filesystem_read"))
        self.assertTrue(effects.is_allowed("wall_clock"))
        self.assertFalse(effects.is_allowed("process_spawn"))


if __name__ == "__main__":
    unittest.main()