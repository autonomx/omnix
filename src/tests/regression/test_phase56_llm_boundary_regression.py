import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.llm_boundary import LLMGateway
from app.rpg.core.llm_recording import LLMRecorder
from app.rpg.validation.state_boundary_validator import StateBoundaryValidator


class _DummyLLM:
    def __init__(self, model="dummy-model"):
        self.calls = []
        self.model = model

    def complete(self, prompt):
        self.calls.append(prompt)
        return f"resp:{prompt}"


class TestPhase56LLMBoundaryRegression(unittest.TestCase):
    def test_recorded_outputs_are_snapshot_serializable(self):
        rec = LLMRecorder()
        rec.record("prompt", "response", {"npc": "guard"}, {"method": "complete", "model": "m1"})
        state = rec.serialize_state()

        rec2 = LLMRecorder()
        rec2.deserialize_state(state)

        self.assertEqual(
            rec2.replay("prompt", {"npc": "guard"}, {"method": "complete", "model": "m1"}),
            "response",
        )

    def test_llm_gateway_no_client_raises_error(self):
        gateway = LLMGateway(
            llm_client=None,
            recorder=LLMRecorder(),
        )

        with self.assertRaises(RuntimeError):
            gateway.call("complete", "any prompt")

    def test_llm_gateway_unsupported_method_raises_error(self):
        gateway = LLMGateway(
            llm_client=_DummyLLM(),
            recorder=LLMRecorder(),
        )

        with self.assertRaises(ValueError):
            gateway.call("unsupported_method", "prompt")

    def test_effect_policy_live_vs_replay(self):
        live_policy = EffectPolicy(
            allow_logs=True,
            allow_metrics=True,
            allow_network=True,
            allow_disk_write=True,
            allow_live_llm=True,
            allow_tool_calls=True,
        )

        replay_policy = EffectPolicy(
            allow_logs=True,
            allow_metrics=True,
            allow_network=False,
            allow_disk_write=False,
            allow_live_llm=False,
            allow_tool_calls=False,
        )

        live_manager = EffectManager(live_policy)
        replay_manager = EffectManager(replay_policy)

        # Live allows everything
        self.assertTrue(live_manager.is_allowed("live_llm"))
        self.assertTrue(live_manager.is_allowed("network"))
        self.assertTrue(live_manager.is_allowed("disk_write"))

        # Replay blocks external effects
        self.assertFalse(replay_manager.is_allowed("live_llm"))
        self.assertFalse(replay_manager.is_allowed("network"))
        self.assertFalse(replay_manager.is_allowed("disk_write"))

    def test_state_boundary_validator_llm_replay_safety(self):
        validator = StateBoundaryValidator()

        gateway = LLMGateway(
            llm_client=_DummyLLM(),
            recorder=LLMRecorder(),
            determinism=DeterminismConfig(use_recorded_llm=True, replay_mode=True),
            effect_manager=EffectManager(EffectPolicy(allow_live_llm=False)),
        )

        result = validator.validate_llm_replay_safety(gateway)
        self.assertTrue(result["ok"], "Expected LLM replay safety validation to pass")

    def test_deterministic_llm_client_with_effect_manager(self):
        """Verify that DeterministicLLMClient properly gates live LLM calls."""
        recorder = LLMRecorder()
        det = DeterminismConfig(record_llm=False, use_recorded_llm=False)
        effects = EffectManager(EffectPolicy(allow_live_llm=False))

        from app.rpg.core.llm_recording import DeterministicLLMClient
        client = DeterministicLLMClient(
            inner_client=_DummyLLM(),
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        # Should block live LLM due to effect policy
        with self.assertRaises(RuntimeError):
            client.complete("hello")

    def test_multiple_records_load_and_replay(self):
        rec = LLMRecorder()
        records_data = [
            ("p1", "r1", {"c": "1"}, {"method": "complete"}),
            ("p2", "r2", {"c": "2"}, {"method": "chat"}),
            ("p3", "r3", {"c": "3"}, {"method": "generate"}),
        ]

        for prompt, response, ctx, cfg in records_data:
            rec.record(prompt, response, ctx, cfg)

        # Verify all records are retrievable
        self.assertEqual(rec.replay("p1", {"c": "1"}, {"method": "complete"}), "r1")
        self.assertEqual(rec.replay("p2", {"c": "2"}, {"method": "chat"}), "r2")
        self.assertEqual(rec.replay("p3", {"c": "3"}, {"method": "generate"}), "r3")

    def test_gateway_mode_switch_preserves_state(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det = DeterminismConfig(record_llm=True)
        effects = EffectManager(EffectPolicy(allow_live_llm=True))

        gateway = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        # Record in live mode
        gateway.set_mode("live")
        out1 = gateway.call("complete", "hello", context={})
        self.assertEqual(out1, "resp:hello")
        self.assertEqual(len(recorder.records), 1)

        # Switch to replay and verify it uses the recording
        gateway.set_mode("replay")
        out2 = gateway.call("complete", "hello", context={})
        self.assertEqual(out2, "resp:hello")
        self.assertEqual(len(llm.calls), 1)  # Should not call LLM again


if __name__ == "__main__":
    unittest.main()