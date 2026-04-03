"""PHASE 5.3 — LLM Record/Replay Layer Regression Tests

Regression tests for:
- Replay without record fails hard (KeyError)
- Record key depends on context (same prompt + different context = different key)
- Record key depends on config (same prompt/context + different method/model = different key)
- Multiple recordings don't override each other
- Cache behavior is consistent
- DeterministicLLMClient includes method/model in config for recording keys
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


class TestPhase53LLMRecordingRegression(unittest.TestCase):
    """Regression tests for Phase 5.3 LLM recording."""

    def test_replay_without_record_fails_hard(self):
        """Test that using replay mode without recording first fails hard."""
        det = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det)

        with self.assertRaises(KeyError):
            llm.complete("unknown", context={"x": 1})

        # Inner LLM should NOT have been called
        self.assertEqual(inner.calls, [])

    def test_record_key_depends_on_context(self):
        """Test that different contexts produce different record keys."""
        rec = LLMRecorder()
        rec.record("prompt", "a", {"npc": "guard"})
        rec.record("prompt", "b", {"npc": "merchant"})

        self.assertEqual(rec.replay("prompt", {"npc": "guard"}), "a")
        self.assertEqual(rec.replay("prompt", {"npc": "merchant"}), "b")

    def test_record_key_depends_on_config(self):
        """Same prompt/context but different method/model config should not collide."""
        rec = LLMRecorder()
        rec.record("prompt", "complete-response", {"npc": "guard"}, {"method": "complete", "model": "m1"})
        rec.record("prompt", "chat-response", {"npc": "guard"}, {"method": "chat", "model": "m1"})
        rec.record("prompt", "other-model-response", {"npc": "guard"}, {"method": "complete", "model": "m2"})

        self.assertEqual(
            rec.replay("prompt", {"npc": "guard"}, {"method": "complete", "model": "m1"}),
            "complete-response",
        )
        self.assertEqual(
            rec.replay("prompt", {"npc": "guard"}, {"method": "chat", "model": "m1"}),
            "chat-response",
        )
        self.assertEqual(
            rec.replay("prompt", {"npc": "guard"}, {"method": "complete", "model": "m2"}),
            "other-model-response",
        )

    def test_multiple_recordings_same_key_override(self):
        """Test that recording same prompt+context twice overrides previous value."""
        rec = LLMRecorder()
        rec.record("prompt", "first", {"npc": "guard"})
        rec.record("prompt", "second", {"npc": "guard"})

        # Should return the most recent recording
        self.assertEqual(rec.replay("prompt", {"npc": "guard"}), "second")
        self.assertEqual(len(rec.records), 2)  # Both records preserved

    def test_deterministic_mode_isolation(self):
        """Test that switching modes doesn't leak state between recordings."""
        # Live mode: record
        det_live = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det_live)

        llm.complete("test1", context={"a": 1})
        llm.complete("test2", context={"b": 2})

        self.assertEqual(len(rec.records), 2)
        self.assertEqual(len(inner.calls), 2)

        # Replay mode: replay one, ignore other
        det_replay = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        inner2 = _DummyLLM()
        llm2 = DeterministicLLMClient(inner2, rec, det_replay)

        result1 = llm2.complete("test1", context={"a": 1})
        self.assertEqual(result1, "resp:test1")
        self.assertEqual(inner2.calls, [])  # No inner LLM calls

        result2 = llm2.complete("test2", context={"b": 2})
        self.assertEqual(result2, "resp:test2")
        self.assertEqual(len(inner2.calls), 0)  # Still no inner LLM calls

    def test_wrapper_uses_method_and_model_in_key(self):
        """DeterministicLLMClient should record/replay with config-sensitive keys."""
        det = DeterminismConfig(record_llm=True, use_recorded_llm=False)
        rec = LLMRecorder()
        inner = _DummyLLM()
        llm = DeterministicLLMClient(inner, rec, det)

        out1 = llm.complete("prompt", context={"npc": "guard"})
        self.assertEqual(out1, "resp:prompt")

        # Replay path with same config should work
        det2 = DeterminismConfig(record_llm=False, use_recorded_llm=True)
        inner2 = _DummyLLM()
        llm2 = DeterministicLLMClient(inner2, rec, det2)
        out2 = llm2.complete("prompt", context={"npc": "guard"})

        self.assertEqual(out2, "resp:prompt")
        self.assertEqual(inner2.calls, [])

    def test_empty_context_vs_default_context(self):
        """Test that empty context and None context both serialize deterministically."""
        rec = LLMRecorder()
        rec.record("prompt", "with_empty", {})

        # The make_key normalizes context={} to {} when None is passed
        # So both None and {} produce the same key
        self.assertEqual(rec.replay("prompt", {}), "with_empty")
        # Since make_key normalizes None -> {}, replay with None will find the {} key
        self.assertEqual(rec.replay("prompt", None), "with_empty")

    def test_complex_context_hashing(self):
        """Test that complex nested contexts produce deterministic keys."""
        rec = LLMRecorder()
        complex_ctx = {
            "npc": {"id": "guard_1", "stats": {"hp": 100, "mp": 50}},
            "goal": "defend",
            "location": {"x": 10, "y": 20},
            "allies": ["warrior", "mage"],
        }

        rec.record("complex_prompt", {"result": "success"}, complex_ctx)
        out = rec.replay("complex_prompt", complex_ctx)

        self.assertEqual(out, {"result": "success"})

    def test_recorder_load_records_isolation(self):
        """Test that load_records clears previous state."""
        rec = LLMRecorder()
        from app.rpg.core.llm_recording import LLMRecord

        # Record some data
        rec.record("initial", "initial_response", {})

        # Load new records (should overwrite)
        rec.load_records([
            LLMRecord(key=rec.make_key("loaded", {}), response="loaded_response"),
        ])

        # Old key should be gone
        with self.assertRaises(KeyError):
            rec.replay("initial", {})

        # New key should work
        self.assertEqual(rec.replay("loaded", {}), "loaded_response")


if __name__ == "__main__":
    unittest.main()