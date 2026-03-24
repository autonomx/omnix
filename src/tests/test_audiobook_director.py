"""
Unit tests for the AI Audiobook Director subsystem.

Tests do not require external services (LLM, TTS, STT).
All modules are tested with deterministic / keyword-based behaviour.
"""

import json
import os
import sys
import tempfile
import pytest

# Ensure src/ is on the path so the audiobook package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# TextSegmenter
# ---------------------------------------------------------------------------

class TestTextSegmenter:
    def _get(self):
        from audiobook.segmentation.text_segmenter import TextSegmenter
        return TextSegmenter()

    def test_short_text_returns_single_segment(self):
        seg = self._get()
        result = seg.segment("Hello world.")
        assert len(result) == 1
        assert "Hello world." in result[0]

    def test_paragraph_splitting(self):
        seg = self._get()
        text = "Para one.\n\nPara two.\n\nPara three."
        result = seg.segment(text)
        assert len(result) >= 1
        combined = " ".join(result)
        assert "Para one" in combined
        assert "Para two" in combined

    def test_long_text_splits(self):
        seg = self._get()
        # Create text longer than MAX_CHARS
        long_text = ("This is a sentence. " * 200)
        result = seg.segment(long_text)
        assert len(result) > 1
        # Each segment should not massively exceed the limit
        for s in result:
            assert len(s) <= seg.MAX_CHARS * 1.5

    def test_empty_text(self):
        seg = self._get()
        result = seg.segment("")
        assert result == [""]


# ---------------------------------------------------------------------------
# SceneDetector
# ---------------------------------------------------------------------------

class TestSceneDetector:
    def _get(self):
        from audiobook.segmentation.scene_detector import SceneDetector
        return SceneDetector()

    def test_single_segment_no_breaks(self):
        det = self._get()
        result = det.detect(["Just some text."])
        assert len(result) == 1
        assert result[0]["scene_id"] == 1

    def test_scene_break_creates_new_scene(self):
        det = self._get()
        segments = ["First scene text.", "***", "Second scene text."]
        result = det.detect(segments)
        assert len(result) == 2

    def test_empty_segments(self):
        det = self._get()
        result = det.detect([])
        assert result == [{"scene_id": 1, "segments": []}]


# ---------------------------------------------------------------------------
# SpeakerTracker
# ---------------------------------------------------------------------------

class TestSpeakerTracker:
    def _get(self):
        from audiobook.ai.speaker_tracker import SpeakerTracker
        return SpeakerTracker()

    def test_known_speaker_returned_as_is(self):
        t = self._get()
        result = t.resolve("Alice")
        assert result == "Alice"

    def test_none_falls_back_to_narrator(self):
        t = self._get()
        result = t.resolve(None)
        assert result == "Narrator"

    def test_alternates_between_two_speakers(self):
        t = self._get()
        t.resolve("Alice")
        t.resolve("Bob")
        # When speaker is unknown, should alternate
        r1 = t.resolve(None)
        r2 = t.resolve(None)
        assert r1 in ("Alice", "Bob")
        assert r2 in ("Alice", "Bob")
        assert r1 != r2  # should alternate


# ---------------------------------------------------------------------------
# CharacterExtractor
# ---------------------------------------------------------------------------

class TestCharacterExtractor:
    def _get(self, llm_fn=None):
        from audiobook.ai.character_extractor import CharacterExtractor
        return CharacterExtractor(llm_fn=llm_fn)

    def test_extract_from_segments(self):
        ext = self._get()
        segments = [
            {"speaker": "Alice", "text": "Hello"},
            {"speaker": "Narrator", "text": "She walked."},
            {"speaker": "Alice", "text": "Bye"},
            {"speaker": "Rabbit", "text": "Late!"},
        ]
        result = ext.extract(segments)
        names = [c["name"] for c in result]
        assert "Alice" in names
        assert "Narrator" in names
        assert "Rabbit" in names
        # No duplicates
        assert len(names) == len(set(names))

    def test_extract_from_text_regex_fallback(self):
        ext = self._get()
        text = 'Alice said "hello". Bob replied "hi".'
        result = ext.extract_from_text(text)
        assert isinstance(result, list)

    def test_extract_from_text_with_mock_llm(self):
        mock_response = '{"characters": ["Alice", "Rabbit", "Queen"]}'
        ext = self._get(llm_fn=lambda p: mock_response)
        result = ext.extract_from_text("Some story text.")
        assert "Alice" in result
        assert "Rabbit" in result
        assert "Queen" in result

    def test_empty_segments(self):
        ext = self._get()
        assert ext.extract([]) == []


# ---------------------------------------------------------------------------
# EmotionDetector
# ---------------------------------------------------------------------------

class TestEmotionDetector:
    def _get(self, llm_fn=None):
        from audiobook.ai.emotion_detector import EmotionDetector
        return EmotionDetector(llm_fn=llm_fn)

    def test_keyword_panic(self):
        det = self._get()
        lines = [{"speaker": "Rabbit", "text": "Run! Danger ahead!"}]
        result = det.detect_batch(lines)
        assert result[0] in ("fear", "panic")

    def test_keyword_happy(self):
        det = self._get()
        lines = [{"speaker": "Alice", "text": "What a wonderful day!"}]
        result = det.detect_batch(lines)
        assert result[0] == "happy"

    def test_neutral_default(self):
        det = self._get()
        lines = [{"speaker": "Narrator", "text": "She walked into the room."}]
        result = det.detect_batch(lines)
        assert result[0] == "neutral"

    def test_empty_batch(self):
        det = self._get()
        assert det.detect_batch([]) == []

    def test_llm_overrides_keyword(self):
        mock_response = '["excited"]'
        det = self._get(llm_fn=lambda p: mock_response)
        lines = [{"speaker": "Alice", "text": "She walked."}]
        result = det.detect_batch(lines)
        assert result[0] == "excited"

    def test_llm_invalid_json_falls_back(self):
        det = self._get(llm_fn=lambda p: "not json")
        lines = [{"speaker": "Narrator", "text": "She walked."}]
        result = det.detect_batch(lines)
        assert result[0] == "neutral"


# ---------------------------------------------------------------------------
# PacingEngine
# ---------------------------------------------------------------------------

class TestPacingEngine:
    def _get(self):
        from audiobook.director.pacing_engine import PacingEngine
        return PacingEngine()

    def test_exclamation_is_fast(self):
        p = self._get()
        line = {"speaker": "Rabbit", "text": "I'm late!"}
        assert p.decide(line) == "fast"

    def test_suspense_scene_is_slow(self):
        p = self._get()
        line = {"speaker": "Narrator", "text": "She waited."}
        assert p.decide(line, scene_mood="suspense") == "slow"

    def test_long_text_is_slow(self):
        p = self._get()
        line = {"speaker": "Narrator", "text": "x" * 250}
        assert p.decide(line) == "slow"

    def test_short_dialogue_is_normal(self):
        p = self._get()
        line = {"speaker": "Alice", "text": "Hello."}
        assert p.decide(line) == "normal"

    def test_pause_question(self):
        p = self._get()
        assert p.pause({"text": "Who are you?"}) == 0.5

    def test_pause_exclamation(self):
        p = self._get()
        assert p.pause({"text": "Stop!"}) == 0.3

    def test_pause_ellipsis(self):
        p = self._get()
        assert p.pause({"text": "She said..."}) == 0.6

    def test_pause_default(self):
        p = self._get()
        assert p.pause({"text": "She walked away."}) == 0.2


# ---------------------------------------------------------------------------
# EmphasisEngine
# ---------------------------------------------------------------------------

class TestEmphasisEngine:
    def _get(self):
        from audiobook.director.emphasis_engine import EmphasisEngine
        return EmphasisEngine()

    def test_detects_keyword(self):
        e = self._get()
        line = {"text": "You must never go there alone."}
        result = e.detect(line)
        assert "never" in result
        assert "alone" in result

    def test_no_keywords(self):
        e = self._get()
        line = {"text": "The sun was setting over the hills."}
        assert e.detect(line) == []

    def test_case_insensitive(self):
        e = self._get()
        line = {"text": "DANGER is everywhere!"}
        assert "danger" in e.detect(line)


# ---------------------------------------------------------------------------
# SceneMoodEngine
# ---------------------------------------------------------------------------

class TestSceneMoodEngine:
    def _get(self, llm_fn=None):
        from audiobook.director.scene_mood_engine import SceneMoodEngine
        return SceneMoodEngine(llm_fn=llm_fn)

    def test_action_keywords(self):
        eng = self._get()
        script = [{"text": "The battle raged and swords clashed!"}]
        assert eng.detect(script) == "action"

    def test_suspense_keywords(self):
        eng = self._get()
        script = [{"text": "A shadow crept through the dark corridor."}]
        assert eng.detect(script) == "suspense"

    def test_default_calm(self):
        eng = self._get()
        script = [{"text": "She sat by the window and read her book."}]
        assert eng.detect(script) == "calm"

    def test_llm_mood(self):
        eng = self._get(llm_fn=lambda p: "romantic")
        script = [{"text": "anything"}]
        assert eng.detect(script) == "romantic"

    def test_llm_invalid_falls_back(self):
        eng = self._get(llm_fn=lambda p: "gibberish_mood")
        script = [{"text": "battle!"}]
        # Should fall back to keyword detection
        assert eng.detect(script) == "action"


# ---------------------------------------------------------------------------
# SFXEngine
# ---------------------------------------------------------------------------

class TestSFXEngine:
    def _get(self):
        from audiobook.director.sfx_engine import SFXEngine
        return SFXEngine()

    def test_detects_thunder(self):
        sfx = self._get()
        assert sfx.detect({"text": "The thunder roared."}) == "thunder"

    def test_detects_footsteps(self):
        sfx = self._get()
        assert sfx.detect({"text": "His footsteps echoed."}) == "footsteps"

    def test_returns_none_for_unknown(self):
        sfx = self._get()
        assert sfx.detect({"text": "She smiled."}) is None


# ---------------------------------------------------------------------------
# AudiobookDirector
# ---------------------------------------------------------------------------

class TestAudiobookDirector:
    def _get(self, llm_fn=None):
        from audiobook.director.audiobook_director import AudiobookDirector
        return AudiobookDirector(llm_fn=llm_fn)

    def test_direct_returns_same_count(self):
        d = self._get()
        script = [
            {"speaker": "Narrator", "text": "She walked."},
            {"speaker": "Alice", "text": "I'm late!"},
        ]
        result = d.direct(script)
        assert len(result) == 2

    def test_directed_has_required_keys(self):
        d = self._get()
        script = [{"speaker": "Alice", "text": "Hello!"}]
        result = d.direct(script)
        assert "emotion" in result[0]
        assert "pace" in result[0]
        assert "emphasis" in result[0]
        assert "pause_after" in result[0]

    def test_exclamation_fast(self):
        d = self._get()
        result = d.direct([{"speaker": "Rabbit", "text": "Run!"}])
        assert result[0]["pace"] == "fast"

    def test_empty_script(self):
        d = self._get()
        assert d.direct([]) == []

    def test_direct_full_script(self):
        d = self._get()
        structured = {
            "title": "Test",
            "characters": [{"id": "alice", "name": "Alice"}],
            "segments": [
                {"scene": 1, "script": [{"speaker": "Alice", "text": "Hello!"}]}
            ],
        }
        result = d.direct_full_script(structured)
        assert result["title"] == "Test"
        assert len(result["segments"]) == 1
        assert result["segments"][0]["script"][0]["pace"] == "fast"


# ---------------------------------------------------------------------------
# CharacterVoiceMemory
# ---------------------------------------------------------------------------

class TestCharacterVoiceMemory:
    def _get(self, tmp_dir):
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        return CharacterVoiceMemory("test_book", base_dir=tmp_dir)

    def test_set_and_get_voice(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Alice", "young_female")
        assert mem.get_voice("Alice") == "young_female"

    def test_persist_and_reload(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Narrator", "deep_male")

        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        reloaded = CharacterVoiceMemory("test_book", base_dir=str(tmp_path))
        assert reloaded.get_voice("Narrator") == "deep_male"

    def test_get_voice_missing_returns_none(self, tmp_path):
        mem = self._get(str(tmp_path))
        assert mem.get_voice("Unknown") is None

    def test_update_profile(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Rabbit", "fast_male", emotion_style="nervous")
        profile = mem.get_profile("Rabbit")
        assert profile["voice"] == "fast_male"
        assert profile["emotion_style"] == "nervous"

        mem.update_profile("Rabbit", {"emotion_style": "panicked"})
        assert mem.get_profile("Rabbit")["emotion_style"] == "panicked"
        assert mem.get_profile("Rabbit")["voice"] == "fast_male"

    def test_remove(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Ghost", "whisper_voice")
        mem.remove("Ghost")
        assert mem.get_voice("Ghost") is None

    def test_all_profiles(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Alice", "young_female")
        mem.set_voice("Narrator", "deep_male")
        profiles = mem.all_profiles()
        assert "alice" in profiles
        assert "narrator" in profiles

    def test_has_character(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("Alice", "young_female")
        assert mem.has_character("Alice")
        assert not mem.has_character("Bob")

    def test_len(self, tmp_path):
        mem = self._get(str(tmp_path))
        mem.set_voice("A", "v1")
        mem.set_voice("B", "v2")
        assert len(mem) == 2

    def test_graceful_corrupt_file(self, tmp_path):
        profile_dir = os.path.join(str(tmp_path), "test_book")
        os.makedirs(profile_dir, exist_ok=True)
        with open(os.path.join(profile_dir, "voice_profiles.json"), "w") as f:
            f.write("NOT_JSON")
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        mem = CharacterVoiceMemory("test_book", base_dir=str(tmp_path))
        assert mem.all_profiles() == {}


# ---------------------------------------------------------------------------
# CharacterNormalizer
# ---------------------------------------------------------------------------

class TestCharacterNormalizer:
    def _get(self, aliases=None):
        from audiobook.voice.character_normalizer import CharacterNormalizer
        return CharacterNormalizer(aliases=aliases)

    def test_explicit_alias(self):
        n = self._get({"Mr. Darcy": "Darcy"})
        assert n.normalize("Mr. Darcy") == "Darcy"

    def test_honorific_strip(self):
        n = self._get()
        # First call: registers "Darcy" as canonical
        n.normalize("Darcy")
        # Second call: "Mr. Darcy" should strip to "Darcy"
        result = n.normalize("Mr. Darcy")
        assert result == "Darcy"

    def test_first_name_match(self):
        n = self._get()
        n.normalize("Alice")           # registers Alice
        result = n.normalize("Alice Liddell")
        assert result == "Alice"

    def test_narrator_passthrough(self):
        n = self._get()
        assert n.normalize("Narrator") == "Narrator"

    def test_empty_string(self):
        n = self._get()
        assert n.normalize("") == ""

    def test_normalize_script(self):
        n = self._get({"Mr. Darcy": "Darcy"})
        script = [
            {"speaker": "Mr. Darcy", "text": "Good evening."},
            {"speaker": "Elizabeth", "text": "Indeed."},
        ]
        result = n.normalize_script(script)
        assert result[0]["speaker"] == "Darcy"
        assert result[1]["speaker"] == "Elizabeth"
        # Text must be unchanged
        assert result[0]["text"] == "Good evening."


# ---------------------------------------------------------------------------
# VoiceAssignment (with memory)
# ---------------------------------------------------------------------------

class TestVoiceAssignmentWithMemory:
    def _get(self, tmp_path, voices=None):
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        from audiobook.voice.character_normalizer import CharacterNormalizer
        from audiobook.voice.voice_assignment import VoiceAssignment
        mem = CharacterVoiceMemory("test", base_dir=str(tmp_path))
        norm = CharacterNormalizer()
        return VoiceAssignment(
            available_voices=voices or ["voice_a", "voice_b", "voice_c"],
            memory=mem,
            normalizer=norm,
        ), mem

    def test_narrator_gets_deep_male(self, tmp_path):
        va, _ = self._get(tmp_path)
        voice = va.get_voice("Narrator")
        assert voice == "deep_male"

    def test_alice_gets_young_female(self, tmp_path):
        va, _ = self._get(tmp_path)
        voice = va.get_voice("Alice")
        assert voice == "young_female"

    def test_voice_persisted_to_memory(self, tmp_path):
        va, mem = self._get(tmp_path)
        va.get_voice("Rabbit")
        # Memory should have saved it
        assert mem.get_voice("Rabbit") is not None

    def test_memory_reused_across_instances(self, tmp_path):
        va1, _ = self._get(tmp_path)
        voice1 = va1.get_voice("SomeCharacter")

        # New instance, same memory store
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        from audiobook.voice.character_normalizer import CharacterNormalizer
        from audiobook.voice.voice_assignment import VoiceAssignment
        mem2 = CharacterVoiceMemory("test", base_dir=str(tmp_path))
        va2 = VoiceAssignment(
            available_voices=["voice_a", "voice_b", "voice_c"],
            memory=mem2,
            normalizer=CharacterNormalizer(),
        )
        voice2 = va2.get_voice("SomeCharacter")
        assert voice1 == voice2

    def test_override_voice(self, tmp_path):
        va, mem = self._get(tmp_path)
        va.override_voice("Alice", "custom_voice")
        assert va.get_voice("Alice") == "custom_voice"
        assert mem.get_voice("Alice") == "custom_voice"

    def test_alias_uses_canonical_memory(self, tmp_path):
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        from audiobook.voice.character_normalizer import CharacterNormalizer
        from audiobook.voice.voice_assignment import VoiceAssignment
        mem = CharacterVoiceMemory("test", base_dir=str(tmp_path))
        norm = CharacterNormalizer({"Mr. Darcy": "Darcy"})
        va = VoiceAssignment(
            available_voices=["voice_a", "voice_b"],
            memory=mem,
            normalizer=norm,
        )
        voice_alias = va.get_voice("Mr. Darcy")
        voice_canonical = va.get_voice("Darcy")
        assert voice_alias == voice_canonical
        # Only one profile saved
        assert len(mem) == 1

    def test_assign_returns_all_characters(self, tmp_path):
        va, _ = self._get(tmp_path)
        result = va.assign(["Alice", "Rabbit", "Narrator"])
        assert set(result.keys()) == {"Alice", "Rabbit", "Narrator"}
        assert all(isinstance(v, str) for v in result.values())
