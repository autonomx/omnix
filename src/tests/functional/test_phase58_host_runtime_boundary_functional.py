"""PHASE 5.8 — Host/Process Boundary — Functional Tests.

These tests verify the HostRuntimeGateway works correctly in realistic
workflows including: recording phase, replay phase, and snapshot integration.
"""

import unittest
import os

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.host_runtime_boundary import (
    HostRuntimeGateway,
    HostRuntimeRecorder,
    DeterministicHostRuntimeClient,
    HostCallSpec,
    HostRuntimeRecord,
)
from app.rpg.core.snapshot_manager import SnapshotManager


class _MockHostRuntime:
    """Simulates a host runtime with env, fs, time, and process operations."""

    def __init__(self):
        self.calls = []
        self._env = {"PATH": "/usr/bin:/usr/local/bin", "HOME": "/home/user"}
        self._dir = {"files": ["a.txt", "b.txt", "c.cfg"]}

    def call(self, op_name, payload):
        self.calls.append((op_name, payload))
        if op_name == "get_env":
            key = payload.get("key", "") if isinstance(payload, dict) else payload
            return {"value": self._env.get(key, "")}
        elif op_name == "list_dir":
            return self._dir
        elif op_name == "wall_time":
            return {"time": 1234567890.0}
        elif op_name == "run_process":
            return {"stdout": "done", "returncode": 0}
        return {}


class TestPhase58HostRuntimeBoundaryFunctional(unittest.TestCase):
    """Functional tests for Phase 5.8 host/runtime boundary."""

    def test_full_record_replay_cycle(self):
        """Test a full record phase followed by replay phase produces same results."""
        recorder = HostRuntimeRecorder()

        # Record phase
        live_runtime = _MockHostRuntime()
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

        # Make several calls
        result1 = gateway_live.call("get_env", {"key": "PATH"})
        result2 = gateway_live.call("list_dir", {"path": "/tmp"})
        result3 = gateway_live.call("wall_time", None)

        self.assertTrue(result1)
        self.assertTrue(result2)
        self.assertTrue(result3)
        self.assertEqual(len(recorder.records), 3)

        # Replay phase
        replay_runtime = _MockHostRuntime()
        det_replay = DeterminismConfig(record_host=False, use_recorded_host=True)

        gateway_replay = HostRuntimeGateway(
            runtime_client=replay_runtime,
            recorder=recorder,
            determinism=det_replay,
        )

        # Replay same calls
        replay1 = gateway_replay.call("get_env", {"key": "PATH"})
        replay2 = gateway_replay.call("list_dir", {"path": "/tmp"})
        replay3 = gateway_replay.call("wall_time", None)

        # Results must match exactly
        self.assertEqual(replay1, result1)
        self.assertEqual(replay2, result2)
        self.assertEqual(replay3, result3)

        # Replay must NOT hit the real runtime
        self.assertEqual(replay_runtime.calls, [])

    def test_deterministic_replay_across_instances(self):
        """Test that replay works across different gateway instances."""
        recorder = HostRuntimeRecorder()

        # Record
        gw1 = HostRuntimeGateway(
            runtime_client=_MockHostRuntime(),
            recorder=recorder,
            determinism=DeterminismConfig(record_host=True),
        )
        gw1.call("get_env", {"key": "HOME"})

        # New gateway for replay
        gw2 = HostRuntimeGateway(
            runtime_client=_MockHostRuntime(),
            recorder=recorder,
            determinism=DeterminismConfig(use_recorded_host=True),
        )
        result = gw2.call("get_env", {"key": "HOME"})
        self.assertIn("/home/user", str(result))

    def test_effect_policy_blocks_dangerous_operations(self):
        """Test that dangerous operations are blocked by default policy."""
        gateway = HostRuntimeGateway(
            runtime_client=_MockHostRuntime(),
            determinism=DeterminismConfig(),
            effect_manager=EffectManager(EffectPolicy()),  # Default: all host ops blocked
        )

        # All host operations should be blocked by default
        for op, payload in [
            ("get_env", {"key": "PATH"}),
            ("list_dir", {"path": "/"}),
            ("wall_time", None),
            ("run_process", {"cmd": "ls"}),
        ]:
            with self.assertRaises(RuntimeError):
                gateway.call(op, payload)

    def test_gateway_mode_switching(self):
        """Test gateway can switch between live and replay mode."""
        recorder = HostRuntimeRecorder()
        gateway = HostRuntimeGateway(
            runtime_client=_MockHostRuntime(),
            recorder=recorder,
            determinism=DeterminismConfig(record_host=True),
            effect_manager=EffectManager(EffectPolicy(
                allow_env_read=True,
                allow_filesystem_read=True,
                allow_wall_clock=True,
                allow_process_spawn=True,
            )),
        )

        # Record in live mode
        gateway.set_mode("live")
        gateway.call("get_env", {"key": "PATH"})
        self.assertEqual(len(recorder.records), 1)

        # Switch to replay mode
        gateway.set_mode("replay")
        gateway.call("get_env", {"key": "PATH"})
        self.assertEqual(len(recorder.records), 1)  # No new record

    def test_host_call_spec_serialization(self):
        """Test HostCallSpec can be used for serialization testing."""
        spec = HostCallSpec(
            op_name="get_env",
            payload={"key": "PATH"},
            context={"npc": "guard"},
            config={"timeout": 30},
        )
        self.assertEqual(spec.op_name, "get_env")
        self.assertEqual(spec.payload, {"key": "PATH"})
        self.assertEqual(spec.context, {"npc": "guard"})
        self.assertEqual(spec.config, {"timeout": 30})

    def test_host_runtime_record_serialization(self):
        """Test HostRuntimeRecord serialization round-trip."""
        rec = HostRuntimeRecord(key="test_key", result={"data": [1, 2, 3]})
        recorder = HostRuntimeRecorder()
        recorder.records.append(rec)
        recorder._map[rec.key] = rec.result

        state = recorder.serialize_state()
        new_recorder = HostRuntimeRecorder()
        new_recorder.deserialize_state(state)

        self.assertEqual(new_recorder.records[0].key, "test_key")
        self.assertEqual(new_recorder.records[0].result, {"data": [1, 2, 3]})
        self.assertEqual(len(new_recorder._map), 1)

    def test_multiple_operations_recorded_independently(self):
        """Test that different operations are recorded with independent keys."""
        recorder = HostRuntimeRecorder()
        gateway = HostRuntimeGateway(
            runtime_client=_MockHostRuntime(),
            recorder=recorder,
            determinism=DeterminismConfig(record_host=True),
            effect_manager=EffectManager(EffectPolicy(
                allow_env_read=True,
                allow_filesystem_read=True,
                allow_wall_clock=True,
                allow_process_spawn=True,
            )),
        )

        # Make different calls
        gateway.call("get_env", {"key": "PATH"})
        gateway.call("get_env", {"key": "HOME"})
        gateway.call("list_dir", {"path": "/tmp"})

        # All should be recorded with unique keys
        self.assertEqual(len(recorder.records), 3)
        keys = [r.key for r in recorder.records]
        self.assertEqual(len(set(keys)), 3)  # All keys unique


if __name__ == "__main__":
    unittest.main()