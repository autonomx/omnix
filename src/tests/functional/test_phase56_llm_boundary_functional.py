import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.effects import EffectManager
from app.rpg.core.game_loop import GameLoop
from app.rpg.core.event_bus import EventBus
from app.rpg.core.llm_recording import LLMRecorder
from app.rpg.ai.branch_ai_evaluator import AIBranchEvaluator


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
    def set_llm_recorder(self, recorder):
        self.recorder = recorder


class _NPC:
    def update(self, intent, event_bus):
        pass
    def set_mode(self, mode):
        self.mode = mode
    def set_effect_manager(self, em):
        self.effect_manager = em
    def set_llm_recorder(self, recorder):
        self.recorder = recorder


class _Renderer:
    def render(self, narrative):
        return narrative
    def set_mode(self, mode):
        self.mode = mode
    def set_effect_manager(self, em):
        self.effect_manager = em
    def set_llm_recorder(self, recorder):
        self.recorder = recorder


class _DummyLLM:
    def __init__(self):
        self.calls = []
        self.model = "phase56-functional"

    def complete(self, prompt):
        self.calls.append(prompt)
        return '{"score": 0.8, "reasoning": "ok", "narrative_quality": 0.8, "goal_alignment": 0.8, "interesting_outcomes": 1}'


class _Director:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def process(self, events, intent, event_bus):
        score = self.evaluator.evaluate(events, context={"intent": intent["text"]})
        return {"score": score}

    def set_mode(self, mode):
        self.mode = mode
        if hasattr(self.evaluator, "set_mode"):
            self.evaluator.set_mode(mode)

    def set_effect_manager(self, em):
        self.effect_manager = em
        if hasattr(self.evaluator, "set_effect_manager"):
            self.evaluator.set_effect_manager(em)

    def set_llm_recorder(self, recorder):
        self.recorder = recorder
        if hasattr(self.evaluator, "set_llm_recorder"):
            self.evaluator.set_llm_recorder(recorder)


class TestPhase56LLMBoundaryFunctional(unittest.TestCase):
    def test_replay_blocks_fresh_llm_and_uses_recorded(self):
        recorder = LLMRecorder()
        llm = _DummyLLM()

        evaluator = AIBranchEvaluator(
            llm_client=llm,
            recorder=recorder,
            determinism=DeterminismConfig(record_llm=True, use_recorded_llm=False),
        )

        loop = GameLoop(
            intent_parser=_Parser(),
            world=_World(),
            npc_system=_NPC(),
            event_bus=EventBus(),
            story_director=_Director(evaluator),
            scene_renderer=_Renderer(),
            effect_manager=EffectManager(),
        )

        loop.set_llm_recorder(recorder)
        loop.set_mode("live")

        # live record
        out1 = loop.story_director.process([], {"text": "wait"}, loop.event_bus)
        self.assertEqual(out1["score"], 0.8)
        self.assertEqual(len(llm.calls), 1)

        # replay should not call inner llm again
        loop.set_mode("replay")
        out2 = loop.story_director.process([], {"text": "wait"}, loop.event_bus)

        self.assertEqual(out2["score"], 0.8)
        self.assertEqual(len(llm.calls), 1)

    def test_llm_recorder_serialization_roundtrip(self):
        recorder = LLMRecorder()
        recorder.record("prompt1", "response1", {"ctx": "a"}, {"method": "complete"})
        recorder.record("prompt2", "response2", {"ctx": "b"}, {"method": "chat"})

        state = recorder.serialize_state()
        self.assertEqual(len(state["records"]), 2)

        new_recorder = LLMRecorder()
        new_recorder.deserialize_state(state)
        self.assertEqual(len(new_recorder.records), 2)
        self.assertEqual(new_recorder.replay("prompt1", {"ctx": "a"}, {"method": "complete"}), "response1")


if __name__ == "__main__":
    unittest.main()