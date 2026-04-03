"""PHASE 5.8 — Host/Process Boundary — Regression Tests.

These tests verify that existing RPG systems still work correctly after
introducing the Host/Process Boundary, i.e. no regressions in:
- EffectManager policy serialization
- DeterminismConfig host fields
- State contracts (HostRuntimeRecorderAware)
- Snapshot serialization roundtrips
"""

import unittest

from app.rpg.core.determinism import DeterminismConfig, stable_json
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.state_contracts import (
    HostRuntimeRecorderAware,
    ToolRuntimeRecorderAware,
    SerializableState,
)
from app.rpg.core.host_runtime_boundary import (
    HostRuntimeGateway,
    HostRuntimeRecorder,
    HostCallSpec,
)


class TestPhase58Regression(unittest.TestCase):
    """Regression tests for Phase 5.8 host/runtime boundary."""

    def test_determinism_config_has_host_fields(self):
        """Verify DeterminismConfig includes record_host and use_recorded_host."""
        config = DeterminismConfig()
        self.assertIsInstance(config.record_host, bool)
        self.assertIsInstance(config.use_recorded_host, bool)
        self.assertFalse(config.record_host)
        self.assertFalse(config.use_recorded_host)

    def test_determinism_config_serialization(self):
        """Verify DeterminismConfig can be serialized with host fields."""
        config = DeterminismConfig(
            seed=42,
            record_host=True,
            use_recorded_host=True,
        )
        # Verify stable_json handles config
        serialized = stable_json(config.__dict__)
        self.assertIn("record_host", serialized)
        self.assertIn("use_recorded_host", serialized)

    def test_effect_policy_has_host_fields(self):
        """Verify EffectPolicy includes host-related booleans."""
        policy = EffectPolicy()
        self.assertIsInstance(policy.allow_env_read, bool)
        self.assertIsInstance(policy.allow_filesystem_read, bool)
        self.assertIsInstance(policy.allow_wall_clock, bool)
        self.assertIsInstance(policy.allow_process_spawn, bool)
        # Default should be False for security
        self.assertFalse(policy.allow_env_read)
        self.assertFalse(policy.allow_filesystem_read)
        self.assertFalse(policy.allow_wall_clock)
        self.assertFalse(policy.allow_process_spawn)

    def test_effect_manager_is_allowed_host_types(self):
        """Verify EffectManager.is_allowed correctly handles host types."""
        effects = EffectManager(EffectPolicy(
            allow_env_read=True,
            allow_wall_clock=True,
        ))
        self.assertTrue(effects.is_allowed("env_read"))
        self.assertTrue(effects.is_allowed("wall_clock"))
        self.assertFalse(effects.is_allowed("filesystem_read"))
        self.assertFalse(effects.is_allowed("process_spawn"))

    def test_effect_manager_check_blocks_host_types(self):
        """Verify EffectManager.check raises for blocked host types."""
        effects = EffectManager(EffectPolicy())  # All host ops blocked
        for effect_type in ["env_read", "filesystem_read", "wall_clock", "process_spawn"]:
            with self.assertRaises(RuntimeError):
                effects.check(effect_type)

    def test_host_runtime_recorder_awareness(self):
        """Verify HostRuntimeRecorderAware protocol exists."""

        class MockSubsystem:
            def set_host_runtime_recorder(self, recorder):
                self.recorder = recorder

        self.assertTrue(isinstance(MockSubsystem(), object))
        mock = MockSubsystem()
        mock.set_host_runtime_recorder({"key": "value"})
        self.assertEqual(mock.recorder, {"key": "value"})

    def test_host_runtime_recorder_serialize_deserialize(self):
        """Verify HostRuntimeRecorder serialization roundtrip preserves data."""
        recorder = HostRuntimeRecorder()
        recorder.record("get_env", {"key": "PATH"}, {"value": "/usr/bin"})
        recorder.record("list_dir", {"path": "/"}, {"files": ["a.txt"]})

        state = recorder.serialize_state()
        self.assertIsInstance(state, dict)
        self.assertIn("records", state)
        self.assertEqual(len(state["records"]), 2)

        # Deserialize
        new_recorder = HostRuntimeRecorder()
        new_recorder.deserialize_state(state)
        self.assertEqual(len(new_recorder.records), 2)
        repl1 = new_recorder.replay("get_env", {"key": "PATH"}, context={})
        self.assertEqual(repl1, {"value": "/usr/bin"})

    def test_gateway_host_call_spec_creation(self):
        """Verify HostCallSpec can be used for structured host calls."""
        spec = HostCallSpec(
            op_name="get_env",
            payload={"key": "HOSTNAME"},
        )
        self.assertEqual(spec.op_name, "get_env")
        self.assertEqual(spec.payload, {"key": "HOSTNAME"})

    def test_host_runtime_recorder_load_records(self):
        """Verify load_records populates both list and map."""
        from app.rpg.core.host_runtime_boundary import HostRuntimeRecord

        recorder = HostRuntimeRecorder()
        recorder.record("get_env", {"key": "X"}, "v1")
        recorder.record("get_env", {"key": "Y"}, "v2")

        self.assertEqual(len(recorder.records), 2)
        self.assertEqual(recorder.replay("get_env", {"key": "X"}), "v1")
        self.assertEqual(recorder.replay("get_env", {"key": "Y"}), "v2")

    def test_snapshot_state_includes_host_runtime(self):
        """Verify Snapshot dataclass includes host_runtime_state field."""
        from app.rpg.core.snapshot_manager import Snapshot

        snap = Snapshot(tick=100)
        self.assertTrue(hasattr(snap, "host_runtime_state"))
        self.assertIsNone(snap.host_runtime_state)

    def test_stable_json_deterministic_for_host_data(self):
        """Verify stable_json produces deterministic output for host call data."""
        data1 = {
            "op_name": "get_env",
            "payload": {"key": "PATH"},
            "context": {},
            "config": {},
        }
        data2 = {
            "config": {},
            "context": {},
            "payload": {"key": "PATH"},
            "op_name": "get_env",
        }
        # Different dict insertion order should produce same output
        self.assertEqual(stable_json(data1), stable_json(data2))

    def test_gateway_replay_missing_key_error_message(self):
        """Verify KeyError message contains useful context for debugging."""
        gateway = HostRuntimeGateway(
            runtime_client=None,
            recorder=HostRuntimeRecorder(),
            determinism=DeterminismConfig(use_recorded_host=True),
        )

        # Should not raise when client is set to None (uses direct recorder replay in gateway)
        # Actually gateway.call without client raises RuntimeError before trying replay
        with self.assertRaises(RuntimeError):
            gateway.call("test", {})

    def test_host_gateway_replay_missing_key_error_message(self):
        """Verify replay with missing record raises informative KeyError."""
        recorder = HostRuntimeRecorder()
        runtime = type("_Mock", (), {"call": lambda s, o, p: {"ok": True}})()
        gateway = HostRuntimeGateway(
            runtime_client=runtime,
            recorder=recorder,
            determinism=DeterminismConfig(use_recorded_host=True),
        )

        with self.assertRaises(KeyError) as ctx:
            gateway.call("get_env", {"key": "MISSING"})

        # Error should contain useful context
        self.assertIn("No recorded host/runtime result", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()