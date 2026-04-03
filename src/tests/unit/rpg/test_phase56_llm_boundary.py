import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager, EffectPolicy
from app.rpg.core.llm_boundary import LLMGateway
from app.rpg.core.llm_recording import LLMRecorder


class _DummyLLM:
    def __init__(self):
        self.calls = []
        self.model = "dummy-phase56-model"

    def complete(self, prompt):
        self.calls.append(("complete", prompt))
        return f"resp:{prompt}"

    def chat(self, messages):
        self.calls.append(("chat", messages))
        return f"chat:{messages}"

    def generate(self, prompt):
        self.calls.append(("generate", prompt))
        return f"gen:{prompt}"


class TestPhase56LLMBoundary(unittest.TestCase):
    def test_live_llm_call_blocked_by_effect_policy(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det = DeterminismConfig(record_llm=False, use_recorded_llm=False)
        effects = EffectManager(EffectPolicy(allow_live_llm=False))

        gateway = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        with self.assertRaises(RuntimeError):
            gateway.call("complete", "hello", context={"npc": "guard"})

        self.assertEqual(llm.calls, [])

    def test_live_llm_call_allowed_and_recorded(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        effects = EffectManager(EffectPolicy(allow_live_llm=True))

        gateway = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        out = gateway.call("complete", "hello", context={"npc": "guard"})
        self.assertEqual(out, "resp:hello")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(len(recorder.records), 1)

    def test_replay_uses_recorded_output_only(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        effects_live = EffectManager(EffectPolicy(allow_live_llm=True))

        gateway_live = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det_live,
            effect_manager=effects_live,
        )
        gateway_live.call("complete", "hello", context={"npc": "guard"})

        replay_llm = _DummyLLM()
        det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True, replay_mode=True)
        effects_replay = EffectManager(EffectPolicy(allow_live_llm=False))

        gateway_replay = LLMGateway(
            llm_client=replay_llm,
            recorder=recorder,
            determinism=det_replay,
            effect_manager=effects_replay,
        )
        out = gateway_replay.call("complete", "hello", context={"npc": "guard"})

        self.assertEqual(out, "resp:hello")
        self.assertEqual(replay_llm.calls, [])

    def test_replay_missing_record_fails_hard(self):
        gateway = LLMGateway(
            llm_client=_DummyLLM(),
            recorder=LLMRecorder(),
            determinism=DeterminismConfig(use_recorded_llm=True, replay_mode=True),
            effect_manager=EffectManager(EffectPolicy(allow_live_llm=False)),
        )

        with self.assertRaises(KeyError):
            gateway.call("complete", "missing", context={"x": 1})

    def test_set_mode_switches_between_replay_and_live(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det = DeterminismConfig()
        effects = EffectManager()

        gateway = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det,
            effect_manager=effects,
        )

        # Set to replay mode
        gateway.set_mode("replay")
        self.assertTrue(det.replay_mode)
        self.assertTrue(det.use_recorded_llm)

        # Set back to live mode
        gateway.set_mode("live")
        self.assertFalse(det.replay_mode)
        self.assertFalse(det.use_recorded_llm)

    def test_set_effect_manager_propagates_to_client(self):
        llm = _DummyLLM()
        recorder = LLMRecorder()
        det = DeterminismConfig()
        effects1 = EffectManager(EffectPolicy(allow_live_llm=False))
        effects2 = EffectManager(EffectPolicy(allow_live_llm=True))

        gateway = LLMGateway(
            llm_client=llm,
            recorder=recorder,
            determinism=det,
            effect_manager=effects1,
        )

        # Should fail with effects1
        with self.assertRaises(RuntimeError):
            gateway.call("complete", "hello", context={})

        # Swap to effects2
        gateway.set_effect_manager(effects2)

        # Should now succeed
        out = gateway.call("complete", "hello", context={})
        self.assertEqual(out, "resp:hello")


if __name__ == "__main__":
    unittest.main()