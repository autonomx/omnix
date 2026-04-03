"""PHASE 5.5 — State Boundary Unit Tests.

Tests for:
- EffectManager policy behavior
- EffectManager is_allowed() method
- EffectManager serialization roundtrip
- StateBoundaryValidator validation
"""

import random
import unittest

from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.snapshot_manager import SnapshotManager
from app.rpg.validation.state_boundary_validator import StateBoundaryValidator


class _DummyStateful:
    """Dummy stateful system for testing serialization roundtrips."""
    def __init__(self):
        self.value = {"x": 1}

    def serialize_state(self):
        return {"value": {"x": self.value["x"]}}

    def deserialize_state(self, state):
        self.value = {"x": state["value"]["x"]}


class TestPhase55EffectManagerPolicies(unittest.TestCase):
    """Test EffectManager policy enforcement."""

    def test_effect_manager_blocks_network_by_default(self):
        mgr = EffectManager()
        with self.assertRaises(RuntimeError):
            mgr.check("network", {"url": "x"})

    def test_effect_manager_allows_live_llm_when_policy_allows(self):
        mgr = EffectManager(
            EffectPolicy(
                allow_logs=True,
                allow_metrics=True,
                allow_network=False,
                allow_disk_write=False,
                allow_live_llm=True,
                allow_tool_calls=False,
            )
        )
        mgr.check("live_llm", {"prompt": "hi"})
        self.assertEqual(mgr.records[-1].effect_type, "live_llm")

    def test_effect_manager_blocks_all_external_effects_by_default(self):
        mgr = EffectManager()
        for effect_type in ("network", "disk_write", "live_llm", "tool_call"):
            with self.subTest(effect_type=effect_type):
                with self.assertRaises(RuntimeError):
                    mgr.check(effect_type, {"payload": "test"})

    def test_effect_manager_allows_logs_and_metrics_by_default(self):
        mgr = EffectManager()
        mgr.check("log", {"message": "test"})
        mgr.check("metric", {"name": "test", "value": 1})
        self.assertEqual(len(mgr.records), 2)


class TestPhase55IsAllowed(unittest.TestCase):
    """Test EffectManager.is_allowed() guard method."""

    def test_is_allowed_returns_true_for_logs(self):
        mgr = EffectManager()
        self.assertTrue(mgr.is_allowed("log"))

    def test_is_allowed_returns_false_for_network(self):
        mgr = EffectManager()
        self.assertFalse(mgr.is_allowed("network"))

    def test_is_allowed_returns_false_for_live_llm_by_default(self):
        mgr = EffectManager()
        self.assertFalse(mgr.is_allowed("live_llm"))

    def test_is_allowed_returns_true_when_policy_allows(self):
        mgr = EffectManager(EffectPolicy(allow_network=True, allow_live_llm=True))
        self.assertTrue(mgr.is_allowed("network"))
        self.assertTrue(mgr.is_allowed("live_llm"))

    def test_is_allowed_returns_false_for_unknown_type(self):
        mgr = EffectManager()
        self.assertFalse(mgr.is_allowed("unknown_effect"))

    def test_is_allowed_does_not_record(self):
        """is_allowed should check policy without adding to records."""
        mgr = EffectManager()
        mgr.is_allowed("network")
        self.assertEqual(len(mgr.records), 0)


class TestPhase55EffectManagerSerialization(unittest.TestCase):
    """Test EffectManager state serialization/deserialization."""

    def test_effect_manager_state_roundtrip(self):
        mgr = EffectManager(EffectPolicy(allow_live_llm=True))
        mgr.check("live_llm", {"prompt": "hi"})
        state = mgr.serialize_state()

        mgr2 = EffectManager()
        mgr2.deserialize_state(state)

        self.assertEqual(mgr2.serialize_state(), state)

    def test_effect_manager_empty_state_roundtrip(self):
        mgr = EffectManager()
        state = mgr.serialize_state()

        mgr2 = EffectManager()
        mgr2.deserialize_state(state)

        self.assertEqual(mgr2.serialize_state(), state)

    def test_effect_manager_isolation(self):
        """Two managers must not interfere."""
        mgr1 = EffectManager(EffectPolicy(allow_live_llm=True))
        mgr2 = EffectManager(EffectPolicy(allow_live_llm=False))

        mgr1.check("live_llm", {"prompt": "test"})
        with self.assertRaises(RuntimeError):
            mgr2.check("live_llm", {"prompt": "test"})

    def test_blocked_effect_is_recorded_before_failure(self):
        mgr = EffectManager()
        with self.assertRaises(RuntimeError):
            mgr.check("network", {"url": "x"})
        self.assertEqual(len(mgr.records), 1)
        self.assertEqual(mgr.records[0].effect_type, "network")


class TestPhase55StateBoundaryValidator(unittest.TestCase):
    """Test StateBoundaryValidator."""

    def test_state_boundary_roundtrip(self):
        validator = StateBoundaryValidator()
        sys = _DummyStateful()
        result = validator.validate_roundtrip(sys)
        self.assertTrue(result["ok"])

    def test_state_boundary_serializable_contract(self):
        validator = StateBoundaryValidator()
        sys = _DummyStateful()
        result = validator.validate_serializable(sys)
        self.assertTrue(result["ok"])


class TestPhase55SnapshotManager(unittest.TestCase):
    """Test SnapshotManager integration with state boundaries."""

    def test_save_and_load_snapshot(self):
        """Verify basic snapshot save/load works."""
        mgr = SnapshotManager()

        class _FakeLoop:
            class _World:
                def serialize_state(self):
                    return {"hp": 100}
                def deserialize_state(self, state):
                    self.hp = state["hp"]
                hp = 50

            class _EffectManager:
                def serialize_state(self):
                    return {"records": []}
                def deserialize_state(self, state):
                    self.restored = True
                restored = False

        loop = _FakeLoop()
        loop.world = _FakeLoop._World()
        loop.effect_manager = _FakeLoop._EffectManager()

        mgr.save_snapshot(1, loop)
        self.assertTrue(mgr.has_snapshot(1))

        # Modify state
        loop.world.hp = 0

        # Restore
        result = mgr.load_snapshot(1, loop)
        self.assertTrue(result)
        self.assertEqual(loop.world.hp, 100)
        self.assertTrue(loop.effect_manager.restored)

    def test_nearest_snapshot(self):
        mgr = SnapshotManager()
        for t in [50, 100, 150]:
            mgr.save_snapshot(t, type("_", (), {"world": None})())

        self.assertIsNone(mgr.nearest_snapshot(10))
        self.assertEqual(mgr.nearest_snapshot(50), 50)
        self.assertEqual(mgr.nearest_snapshot(75), 50)
        self.assertEqual(mgr.nearest_snapshot(125), 100)
        self.assertEqual(mgr.nearest_snapshot(999), 150)

    def test_snapshot_manager_roundtrip_effect_state(self):
        """SnapshotManager must save and restore effect manager state."""
        class _Loop:
            def __init__(self):
                self.effect_manager = EffectManager(EffectPolicy(allow_live_llm=True))
                self.world = None
                self.npc_system = None
                self.story_director = None
                self.event_bus = None
                self.rng = None
                self.npc_planner = None

        loop = _Loop()
        loop.effect_manager.check("live_llm", {"prompt": "x"})

        sm = SnapshotManager(snapshot_interval=1)
        sm.save_snapshot(1, loop)

        loop2 = _Loop()
        loop2.effect_manager = EffectManager()
        ok = sm.load_snapshot(1, loop2)

        self.assertTrue(ok)
        self.assertEqual(
            loop.effect_manager.serialize_state(),
            loop2.effect_manager.serialize_state(),
        )


class TestPhase55EffectManagerSetPolicy(unittest.TestCase):
    """Test EffectManager.set_policy for mode switching."""

    def test_set_policy_allows_network(self):
        mgr = EffectManager()
        with self.assertRaises(RuntimeError):
            mgr.check("network", {"url": "x"})

        mgr.set_policy(EffectPolicy(allow_network=True))
        mgr.check("network", {"url": "x"})
        self.assertEqual(mgr.records[-1].effect_type, "network")

    def test_set_policy_blocks_live_llm(self):
        mgr = EffectManager(EffectPolicy(allow_live_llm=True))
        mgr.check("live_llm", {"prompt": "hi"})

        mgr.set_policy(EffectPolicy(allow_live_llm=False))
        with self.assertRaises(RuntimeError):
            mgr.check("live_llm", {"prompt": "hi"})


class TestPhase55ModePolicyCorrectness(unittest.TestCase):
    """Test that effect policies are correctly set for each mode."""

    def test_live_mode_effect_policy(self):
        mgr = EffectManager()
        mgr.set_policy(EffectPolicy(
            allow_logs=True,
            allow_metrics=True,
            allow_network=True,
            allow_disk_write=True,
            allow_live_llm=True,
            allow_tool_calls=True,
        ))
        for effect_type in ("log", "metric", "network", "disk_write", "live_llm", "tool_call"):
            with self.subTest(effect_type=effect_type):
                mgr.check(effect_type, {})  # Should NOT raise

    def test_replay_mode_effect_policy(self):
        mgr = EffectManager()
        mgr.set_policy(EffectPolicy(
            allow_logs=True,
            allow_metrics=True,
            allow_network=False,
            allow_disk_write=False,
            allow_live_llm=False,
            allow_tool_calls=False,
        ))
        for effect_type in ("network", "disk_write", "live_llm", "tool_call"):
            with self.subTest(effect_type=effect_type):
                with self.assertRaises(RuntimeError):
                    mgr.check(effect_type, {})


if __name__ == "__main__":
    unittest.main()