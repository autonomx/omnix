"""PHASE 5.3 — LLM Record/Replay Layer Unit Tests

Tests for:
- LLMRecorder record/replay roundtrip
- Missing key raises KeyError
- DeterministicLLMClient records in live mode
- DeterministicLLMClient replays without calling inner LLM
- Config-aware keying (method/model)
"""

import unittest

from app.rpg.core.determinism import DeterminismConfig
from app.rpg.core.llm_recording import LLMRecorder, DeterministicLLMClient


class _DummyLLM:
    """Mock LLM client that returns predictable responses."""

    def __init__(self):
        self.calls = []
        self.model = "dummy-model-v1"

    def complete(self, prompt):
        self.calls.append(prompt)
        return f"resp:{prompt}"

    def chat(self, messages):
        self.calls.append(messages)
        return f"chat:{messages}"

    def generate(self, prompt):
        self.calls.append(prompt)
        return f"gen:{prompt}"


class TestPhase53LLMRecording(unittest.TestCase):
    """Unit tests for Phase 5.3 LLM recording functionality."""

    def test_recorder_roundtrip(self):
        """Test that recorded responses can be replayed."""
        rec = LLMRecorder()
        rec.record("hello", {"score": 0.8}, {"npc": "guard"})
        out = rec.replay("hello", {"npc": "guard"})
        self.assertEqual(out, {"score": 0.8})

    def test_replay_missing_key_raises(self):
        """Test that replay without recording raises KeyError."""
        rec = LLMRecorder()
        with self.assertRaises(KeyError):
            rec.replay("missing", {})

    def test_deterministic_llm_records_in_live_mode(self):
        """Test that live mode with record_llm=True records responses."""
        det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det)

        out = llm.complete("test", context={"a": 1})
        self.assertEqual(out, "resp:test")
        self.assertEqual(len(rec.records), 1)
        self.assertEqual(inner.calls, ["test"])

    def test_deterministic_llm_replays_without_calling_inner(self):
        """Test that replay mode doesn't call inner LLM."""
        # First record in live mode
        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner_record = _DummyLLM()
        llm_record = DeterministicLLMClient(inner_record, rec, det_live)
        llm_record.complete("test", context={"a": 1})

        # Now replay
        det = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        inner_replay = _DummyLLM()
        llm = DeterministicLLMClient(inner_replay, rec, det)

        out = llm.complete("test", context={"a": 1})
        self.assertEqual(out, "resp:test")
        self.assertEqual(inner_replay.calls, [])

    def test_deterministic_llm_chat(self):
        """Test that DeterministicLLMClient.chat works correctly."""
        det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det)

        messages = [{"role": "user", "content": "hello"}]
        out = llm.chat(messages, context={"npc": "guard"})
        self.assertEqual(out, "chat:" + str(messages))
        self.assertEqual(len(rec.records), 1)

    def test_deterministic_llm_generate(self):
        """Test that DeterministicLLMClient.generate works correctly."""
        det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det)

        out = llm.generate("seed", context={"npc": "merchant"})
        self.assertEqual(out, "gen:seed")
        self.assertEqual(len(rec.records), 1)

    def test_load_records(self):
        """Test loading pre-recorded LLM interactions."""
        rec = LLMRecorder()
        from app.rpg.core.llm_recording import LLMRecord

        k1 = rec.make_key("test_prompt", {"ctx": "a"})
        k2 = rec.make_key("test_prompt2", {"ctx": "b"})

        rec.load_records([
            LLMRecord(key=k1, response="r1"),
            LLMRecord(key=k2, response="r2"),
        ])
        self.assertEqual(rec.replay("test_prompt", {"ctx": "a"}), "r1")
        self.assertEqual(rec.replay("test_prompt2", {"ctx": "b"}), "r2")

    def test_recorder_context_differentiation(self):
        """Test that different contexts produce different keys."""
        rec = LLMRecorder()
        rec.record("same_prompt", "response_a", {"npc": "guard"})
        rec.record("same_prompt", "response_b", {"npc": "merchant"})

        self.assertEqual(rec.replay("same_prompt", {"npc": "guard"}), "response_a")
        self.assertEqual(rec.replay("same_prompt", {"npc": "merchant"}), "response_b")


if __name__ == "__main__":
    unittest.main()