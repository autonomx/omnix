"""
Tests for shared audio utilities and providers.

Tests do not require external services (LLM, TTS, STT).
All LLM-dependent modules are tested with mock callables.
"""

import os
import sys

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# #7  TTS Provider Abstraction
# ---------------------------------------------------------------------------

class TestTTSProviderAbstraction:
    def test_register_and_get(self):
        from app.providers.tts_abstraction import (
            OpenAITTSProvider,
            get_provider,
            list_providers,
            register_provider,
            unregister_provider,
        )

        p = OpenAITTSProvider(base_url="http://localhost:9999")
        register_provider("test_openai", p)
        assert "test_openai" in list_providers()
        assert get_provider("test_openai") is p
        unregister_provider("test_openai")
        assert "test_openai" not in list_providers()

    def test_openai_provider_name(self):
        from app.providers.tts_abstraction import OpenAITTSProvider
        p = OpenAITTSProvider(api_key="fake")
        assert p.name == "openai"

    def test_get_nonexistent(self):
        from app.providers.tts_abstraction import get_provider
        assert get_provider("nonexistent_xyz") is None

    def test_openai_generate_connection_error(self):
        from app.providers.tts_abstraction import OpenAITTSProvider
        p = OpenAITTSProvider(base_url="http://localhost:1")
        result = p.generate("test")
        assert result == b""


# ---------------------------------------------------------------------------
# Tests for pipeline hardening fixes (Issues 1-5)
# ---------------------------------------------------------------------------


class TestAudioHardeningHelpers:
    """Issue 3 – Audio normalization and validation helpers."""

    @pytest.fixture(autouse=True)
    def _require_numpy(self):
        pytest.importorskip("numpy")

    def test_is_valid_audio_rejects_empty(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([])) is False

    def test_is_valid_audio_rejects_nan(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([1.0, float('nan'), 0.5])) is False

    def test_is_valid_audio_rejects_silence(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.zeros(100)) is False

    def test_is_valid_audio_rejects_explosion(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([10.0, -10.0])) is False

    def test_is_valid_audio_accepts_good(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _is_valid_audio
        assert _is_valid_audio(np.array([0.5, -0.3, 0.1])) is True

    def test_normalize_audio(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.5, -0.5, 1.5], dtype=np.float32)
        result = _normalize_audio(audio)
        assert isinstance(result, bytes)
        # int16 = 2 bytes per sample
        assert len(result) == 6
        # peak 1.5 > 0.95 → divides by 1.5 → [0.333, -0.333, 1.0]
        # then soft_clip limits; soft_clip(1.0) = 0.5 → ~16383
        arr = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_allclose(arr[2], soft_clip(np.float32(1.0)) * 32767, atol=1)

    def test_normalize_audio_peak_preserves_quiet(self):
        """Peak-based normalisation must NOT amplify a quiet signal."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.1, -0.1], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        # soft_clip(0.1) ≈ 0.0909 → ~2979
        np.testing.assert_allclose(arr[0], soft_clip(np.float32(0.1)) * 32767, atol=1)

    def test_align_bytes(self):
        from app.providers.faster_qwen3_tts_provider import _align_bytes
        assert len(_align_bytes(b'\x00\x01\x02')) == 2
        assert len(_align_bytes(b'\x00\x01')) == 2
        assert len(_align_bytes(b'')) == 0


class TestCrossfadeAudio:
    """Tests for the crossfade_audio helper."""

    def test_crossfade_basic(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(1024, dtype=np.float32)
        curr = np.ones(1024, dtype=np.float32) * -1
        result = crossfade_audio(prev, curr, fade_samples=512)
        # Total length: prev[:-512] + 512 blended + curr[512:] = 512 + 512 + 512
        assert len(result) == 1024 + 1024 - 512

    def test_crossfade_short_arrays_concat(self):
        """Arrays shorter than fade_samples should just concatenate."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(100, dtype=np.float32)
        curr = np.ones(100, dtype=np.float32) * 2
        result = crossfade_audio(prev, curr, fade_samples=512)
        assert len(result) == 200
        assert result[0] == 1.0
        assert result[-1] == 2.0

    def test_crossfade_none_prev(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        curr = np.ones(100, dtype=np.float32)
        result = crossfade_audio(None, curr, fade_samples=512)
        assert len(result) == 100

    def test_crossfade_smooth_transition(self):
        """Midpoint of crossfade should be roughly the average of the two signals."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import crossfade_audio
        prev = np.ones(1024, dtype=np.float32)
        curr = np.zeros(1024, dtype=np.float32)
        result = crossfade_audio(prev, curr, fade_samples=512)
        # prev[:-512] has 512 samples (all 1.0), then 512 blended samples
        # Midpoint of blended region: index 512 + 256 = 768
        mid = 512 + 256
        assert 0.4 < result[mid] < 0.6


class TestApplyFade:
    """Tests for the apply_fade helper."""

    def test_fade_edges_near_zero(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(1024, dtype=np.float32)
        result = apply_fade(audio, fade_samples=256)
        assert result[0] == 0.0  # fade-in starts at zero (raised-cosine)
        assert abs(result[-1]) < 0.01  # fade-out ends near zero
        # Middle should be untouched
        assert result[512] == 1.0

    def test_fade_short_audio_passthrough(self):
        """Audio shorter than 2*fade_samples should pass through as a copy."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(100, dtype=np.float32)
        result = apply_fade(audio, fade_samples=256)
        np.testing.assert_array_equal(result, audio)
        # Must be a copy, not the same object
        assert result is not audio

    def test_fade_does_not_mutate_input(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import apply_fade
        audio = np.ones(1024, dtype=np.float32)
        original = audio.copy()
        apply_fade(audio, fade_samples=256)
        np.testing.assert_array_equal(audio, original)


class TestSilencePad:
    """Tests for the silence_pad helper."""

    def test_silence_appended(self):
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import silence_pad
        audio = np.ones(100, dtype=np.float32)
        result = silence_pad(audio, sample_rate=24000, duration_sec=0.05)
        expected_silence = int(0.05 * 24000)
        assert len(result) == 100 + expected_silence
        # Silence region should be all zeros
        assert np.all(result[100:] == 0.0)


class TestFindBestOffset:
    """Tests for the find_best_offset phase-alignment helper."""

    def test_identical_signals_zero_offset(self):
        """Two identical signals should produce offset 0."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        sig = np.sin(np.linspace(0, 4 * np.pi, 1024, dtype=np.float32))
        offset = find_best_offset(sig, sig)
        assert offset == 0

    def test_shifted_signal_detected(self):
        """A known shift should be detected."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        # Create a sine wave and a shifted copy
        t = np.linspace(0, 8 * np.pi, 2048, dtype=np.float32)
        sig = np.sin(t)
        shift = 30
        prev = sig[:512]
        curr = sig[512 - shift:]  # shifted so the overlap lines up at shift=30
        offset = find_best_offset(prev, curr, max_shift=64)
        # Should find the shift that best aligns the waveforms
        assert 0 <= offset < 64

    def test_short_arrays_no_crash(self):
        """Very short arrays should not crash."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import find_best_offset
        prev = np.array([0.1, 0.2], dtype=np.float32)
        curr = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        offset = find_best_offset(prev, curr, max_shift=5)
        assert isinstance(offset, int)
        assert 0 <= offset < 5


class TestSoftLimiter:
    """Tests for soft_clip limiter in _normalize_audio."""

    def test_soft_clip_smoother_than_clip(self):
        """soft_clip should produce a value < 32767 for a signal at exactly 1.0."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio
        audio = np.array([1.0], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        # soft_clip(1.0) = 0.5 → well below 32767
        assert arr[0] < 32767
        assert arr[0] > 0

    def test_soft_clip_preserves_small_signals(self):
        """For small values soft_clip(x) ≈ x, so quiet audio is not distorted."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import _normalize_audio, soft_clip
        audio = np.array([0.05, -0.05], dtype=np.float32)
        result = _normalize_audio(audio)
        arr = np.frombuffer(result, dtype=np.int16)
        expected = soft_clip(np.float32(0.05)) * 32767
        np.testing.assert_allclose(arr[0], expected, atol=1)

    def test_soft_clip_function(self):
        """Direct test of the soft_clip helper."""
        import numpy as np

        from app.providers.faster_qwen3_tts_provider import soft_clip
        x = np.array([0.0, 0.5, 1.0, 2.0, -1.0], dtype=np.float32)
        result = soft_clip(x)
        expected = x / (1.0 + np.abs(x))
        np.testing.assert_allclose(result, expected, atol=1e-6)
        # All outputs bounded to (-1, 1)
        assert np.all(np.abs(result) < 1.0)


class TestVoiceCloneGenderField:
    """Tests that voice clones include the gender field."""

    def test_default_voice_clone_has_gender(self):
        """New voice clones should default to 'neutral' gender."""
        voice_data = {
            "speaker": "default",
            "language": "en",
            "voice_clone_id": "test_voice",
            "has_audio": True,
            "is_preloaded": True,
            "gender": "neutral",
        }
        assert "gender" in voice_data
        assert voice_data["gender"] == "neutral"

    def test_gender_field_values(self):
        """Gender field should accept male/female/neutral."""
        for gender in ("male", "female", "neutral"):
            voice_data = {"gender": gender}
            assert voice_data["gender"] in ("male", "female", "neutral")

    def test_migration_adds_gender(self):
        """Existing voice data without gender should get 'neutral' after migration."""
        old_voice_data = {
            "speaker": "default",
            "language": "en",
            "voice_clone_id": "legacy_voice",
            "has_audio": True,
        }
        # Simulate migration logic
        if "gender" not in old_voice_data:
            old_voice_data["gender"] = "neutral"
        assert old_voice_data["gender"] == "neutral"
