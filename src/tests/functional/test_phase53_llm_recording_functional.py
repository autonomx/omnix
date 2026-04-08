"""PHASE 5.3 — LLM Record/Replay Layer Functional Tests

Tests end-to-end functionality of LLM recording with the branch evaluator:
- Record during live run
- Replay during replay run
- No LLM calls during replay
- Same output in both modes
- Replay mode uses recorded outputs without inner LLM calls
"""

import unittest

from app.rpg.ai.branch_ai_evaluator import AIBranchEvaluator
from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.llm_recording import LLMRecorder


class _DummyLLM:
    """Mock LLM client that returns deterministic JSON responses."""

    def __init__(self):
        self.calls = []
        self.model = "dummy-branch-model"

    def complete(self, prompt):
        self.calls.append(prompt)
        return '{"score": 0.9, "reasoning": "good branch", "narrative_quality": 0.85, "goal_alignment": 0.92, "interesting_outcomes": 2}'


class TestPhase53LLMRecordingFunctional(unittest.TestCase):
    """Functional tests for Phase 5.3 LLM recording."""

    def test_branch_evaluator_records_then_replays(self):
        """Test that evaluator records in live mode and replays without LLM in replay mode."""
        recorder = LLMRecorder()
        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        llm = _DummyLLM()

        evaluator_live = AIBranchEvaluator(
            llm_client=llm,
            recorder=recorder,
            determinism=det_live,
        )

        from app.rpg.core.event_bus import Event

        events = [Event(type="npc_intent", payload={"npc": "guard"})]
        context = {"npc": "guard", "goal": "survive"}

        live_result = evaluator_live.evaluate(events, context=context)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(len(recorder.records), 1)
        self.assertAlmostEqual(live_result, 0.9, places=1)

        # Replay mode - should not call LLM
        det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        replay_llm = _DummyLLM()
        evaluator_replay = AIBranchEvaluator(
            llm_client=replay_llm,
            recorder=recorder,
            determinism=det_replay,
        )

        replay_result = evaluator_replay.evaluate(events, context=context)

        self.assertEqual(live_result, replay_result)
        self.assertEqual(replay_llm.calls, [])

    def test_branch_evaluator_detailed_evaluation_deterministic(self):
        """Test detailed evaluation is deterministic across live/replay."""
        recorder = LLMRecorder()
        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        llm = _DummyLLM()

        evaluator_live = AIBranchEvaluator(
            llm_client=llm,
            recorder=recorder,
            determinism=det_live,
        )

        from app.rpg.core.event_bus import Event

        events = [Event(type="combat", payload={"actor": "guard"})]
        context = {"npc": "guard", "goal": "attack"}

        live_eval = evaluator_live.evaluate_detailed(events, context)

        # Replay mode
        det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        replay_llm = _DummyLLM()
        evaluator_replay = AIBranchEvaluator(
            llm_client=replay_llm,
            recorder=recorder,
            determinism=det_replay,
        )

        replay_eval = evaluator_replay.evaluate_detailed(events, context)

        self.assertEqual(live_eval.score, replay_eval.score)
        self.assertEqual(live_eval.narrative_quality, replay_eval.narrative_quality)
        self.assertEqual(live_eval.goal_alignment, replay_eval.goal_alignment)
        self.assertEqual(replay_llm.calls, [])

    def test_replay_mode_uses_recorded_outputs_only(self):
        """Recorded evaluator outputs should be reusable in replay-style mode without inner LLM calls."""
        recorder = LLMRecorder()

        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False, replay_mode=False)
        live_llm = _DummyLLM()
        evaluator_live = AIBranchEvaluator(
            llm_client=live_llm,
            recorder=recorder,
            determinism=det_live,
        )

        from app.rpg.core.event_bus import Event
        events = [Event(type="npc_intent", payload={"npc": "guard", "goal": "protect"})]
        context = {"npc": "guard", "goal": "protect"}

        live_score = evaluator_live.evaluate(events, context=context)
        self.assertEqual(len(live_llm.calls), 1)
        self.assertEqual(len(recorder.records), 1)

        det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True, replay_mode=True)
        replay_llm = _DummyLLM()
        evaluator_replay = AIBranchEvaluator(
            llm_client=replay_llm,
            recorder=recorder,
            determinism=det_replay,
        )

        replay_score = evaluator_replay.evaluate(events, context=context)

        self.assertEqual(live_score, replay_score)
        self.assertEqual(replay_llm.calls, [])


if __name__ == "__main__":
    unittest.main()