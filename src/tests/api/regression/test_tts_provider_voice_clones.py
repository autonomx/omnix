"""
Regression tests for the voice_clones_dir bug in FasterQwen3TTS provider.

Bug: In generate_audio(), `voice_clones_dir` was only assigned inside
the `if speaker:` block, causing an UnboundLocalError when speaker was
None or empty. This broke podcast audio generation entirely.

See: faster_qwen3_tts_provider.py generate_audio()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the import path
SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Helpers – build a provider instance with heavy deps mocked out
# ---------------------------------------------------------------------------

def _make_provider():
    """
    Create a FasterQwen3TTSProvider with its heavy imports stubbed out
    so the tests can run without CUDA / faster-qwen3-tts installed.
    """
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    config = {
        "model_name": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "device": "cpu",
        "dtype": "float32",
        "max_seq_len": 2048,
    }
    provider = FasterQwen3TTSProvider(config)
    return provider


# ---------------------------------------------------------------------------
# Tests for generate_audio – voice_clones_dir regression
# ---------------------------------------------------------------------------


class TestGenerateAudioVoiceClonesDir:
    """Ensure generate_audio never raises UnboundLocalError for voice_clones_dir."""

    def test_no_speaker_no_crash(self, tmp_path):
        """generate_audio(speaker=None) must not raise UnboundLocalError."""
        provider = _make_provider()

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            # No wav files exist → should return error dict, NOT raise
            result = provider.generate_audio("Hello world", speaker=None, language="en")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "No reference audio" in result["error"]

    def test_empty_speaker_no_crash(self, tmp_path):
        """generate_audio(speaker='') must not raise UnboundLocalError."""
        provider = _make_provider()

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            result = provider.generate_audio("Hello world", speaker="", language="en")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "No reference audio" in result["error"]

    def test_no_speaker_with_default_ref(self, tmp_path):
        """When speaker is None but default_ref.wav exists, it should be used."""
        provider = _make_provider()
        default_wav = tmp_path / "default_ref.wav"
        default_wav.write_bytes(b"RIFF" + b"\x00" * 40 + b"WAVE")

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            # Mock _get_model to avoid loading the real model
            with patch.object(provider, "_get_model") as mock_model:
                mock_model.return_value = MagicMock()
                # The method will try to use the model – just verify it gets past
                # the voice_clones_dir resolution without crashing.
                # It will fail later at actual generation, but that's expected.
                result = provider.generate_audio("Hello", speaker=None, language="en")

        # It shouldn't have errored about missing reference audio
        if not result["success"]:
            assert "No reference audio" not in result.get("error", "")

    def test_no_speaker_fallback_to_any_wav(self, tmp_path):
        """When speaker is None and no default_ref.wav, any .wav file is used."""
        provider = _make_provider()
        (tmp_path / "random_voice.wav").write_bytes(b"RIFF" + b"\x00" * 40 + b"WAVE")

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            with patch.object(provider, "_get_model") as mock_model:
                mock_model.return_value = MagicMock()
                result = provider.generate_audio("Hello", speaker=None, language="en")

        if not result["success"]:
            assert "No reference audio" not in result.get("error", "")

    def test_speaker_provided_ref_exists(self, tmp_path):
        """When a named speaker's wav exists, it should be selected."""
        provider = _make_provider()
        (tmp_path / "alice.wav").write_bytes(b"RIFF" + b"\x00" * 40 + b"WAVE")

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            with patch.object(provider, "_get_model") as mock_model:
                mock_model.return_value = MagicMock()
                result = provider.generate_audio("Hello", speaker="alice", language="en")

        if not result["success"]:
            assert "No reference audio" not in result.get("error", "")

    def test_speaker_provided_ref_missing_falls_through(self, tmp_path):
        """When named speaker wav is missing, fallback logic must not crash."""
        provider = _make_provider()
        # No wav files at all
        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            result = provider.generate_audio("Hello", speaker="nonexistent", language="en")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "No reference audio" in result["error"]


# ---------------------------------------------------------------------------
# Tests for generate_audio_stream – confirm it was already correct
# ---------------------------------------------------------------------------


class TestGenerateAudioStreamVoiceClonesDir:
    """Verify generate_audio_stream handles missing speaker without crashing."""

    def test_no_speaker_stream_no_crash(self, tmp_path):
        """generate_audio_stream(speaker=None) must not raise UnboundLocalError."""
        provider = _make_provider()

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            # No wav files → should raise Exception (not UnboundLocalError)
            with pytest.raises(Exception, match="No reference audio"):
                # Consume the generator
                list(provider.generate_audio_stream("Hello", speaker=None, language="en"))

    def test_empty_speaker_stream_no_crash(self, tmp_path):
        """generate_audio_stream(speaker='') must not raise UnboundLocalError."""
        provider = _make_provider()

        with patch("app.providers.faster_qwen3_tts_provider.VOICE_CLONES_DIR", str(tmp_path)):
            with pytest.raises(Exception, match="No reference audio"):
                list(provider.generate_audio_stream("Hello", speaker="", language="en"))
