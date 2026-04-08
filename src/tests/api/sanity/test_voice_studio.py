"""
Tests for Voice Studio blueprint.
Tests the HTTP interface without requiring external services.
"""

import base64
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from app.voice_studio import voice_studio_bp
from flask import Flask


@pytest.fixture
def vs_app():
    """Create a minimal Flask app with only the voice_studio blueprint."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(voice_studio_bp)
    return app


@pytest.fixture
def vs_client(vs_app):
    """Create a test client for the voice studio app."""
    return vs_app.test_client()


# -----------------------------------------------------------------
# Helper
# -----------------------------------------------------------------

def _fake_provider(audio=b"audio"):
    provider = MagicMock()
    provider.provider_name = "mock"
    mock_response = {
        "success": True,
        "audio": base64.b64encode(audio).decode("utf-8"),
        "sample_rate": 24000,
    }
    provider.generate_tts.return_value = mock_response
    provider.generate_audio.return_value = mock_response
    return provider


# -----------------------------------------------------------------
# POST /api/voice_studio/generate  – validation
# -----------------------------------------------------------------


class TestVoiceStudioGenerate:
    """Test POST /api/voice_studio/generate endpoint."""

    def test_empty_text_returns_error(self, vs_client):
        """Empty text should return 400."""
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": "", "voice_id": "default"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "Text is required" in data["error"]

    def test_whitespace_only_text_returns_error(self, vs_client):
        """Whitespace-only text should return 400."""
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": "   ", "voice_id": "default"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False

    def test_missing_voice_returns_error(self, vs_client):
        """Missing voice_id should return 400."""
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": "Hello world"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "Voice is required" in data["error"]

    def test_text_too_long_returns_error(self, vs_client):
        """Text exceeding 2000 chars should return 400."""
        long_text = "A" * 2001
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": long_text, "voice_id": "default"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "2000" in data["error"]

    def test_speed_out_of_range_returns_error(self, vs_client):
        """Speed outside 0.7–1.5 should return 400."""
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": "Hello", "voice_id": "default", "speed": 2.0},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "Speed" in data["error"]

    def test_pitch_out_of_range_returns_error(self, vs_client):
        """Pitch outside -5–5 should return 400."""
        response = vs_client.post(
            "/api/voice_studio/generate",
            json={"text": "Hello", "voice_id": "default", "pitch": 10},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "Pitch" in data["error"]

    def test_valid_input_with_mock_tts(self, vs_client):
        """Valid input with a mock TTS provider should return audio."""
        mock_provider = _fake_provider(b"RIFF\x00\x00\x00\x00WAVE")

        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.get_tts_provider.return_value = mock_provider

            response = vs_client.post(
                "/api/voice_studio/generate",
                json={"text": "Hello world", "voice_id": "default"},
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "audio_base64" in data

    def test_emotion_fallback_applied(self, vs_client):
        """When speed==1.0 and pitch==0, emotion presets should be applied."""
        mock_provider = _fake_provider()

        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.get_tts_provider.return_value = mock_provider

            response = vs_client.post(
                "/api/voice_studio/generate",
                json={
                    "text": "I am happy",
                    "voice_id": "default",
                    "emotion": "happy",
                    "speed": 1.0,
                    "pitch": 0,
                },
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

    def test_no_tts_provider_returns_error(self, vs_client):
        """If no TTS provider available, should return 500."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.get_tts_provider.return_value = None

            response = vs_client.post(
                "/api/voice_studio/generate",
                json={"text": "Hello", "voice_id": "default"},
                content_type="application/json",
            )

        assert response.status_code == 500
        data = response.json
        assert data["success"] is False
        assert "No TTS provider" in data["error"]


# -----------------------------------------------------------------
# GET /api/voice_studio/voices
# -----------------------------------------------------------------


class TestVoiceStudioVoices:
    """Test GET /api/voice_studio/voices endpoint."""

    def test_list_voices_returns_default_when_empty(self, vs_client):
        """Should return at least one default voice if none configured."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.get_tts_provider.return_value = None

            response = vs_client.get("/api/voice_studio/voices")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert len(data["voices"]) >= 1

    def test_list_voices_includes_custom_voices(self, vs_client):
        """Should include custom voices from shared state."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {
                "test_voice": {"gender": "female", "voice_clone_id": "test_voice"},
            }
            mock_shared.get_tts_provider.return_value = None

            response = vs_client.get("/api/voice_studio/voices")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert any(v["id"] == "test_voice" for v in data["voices"])


# -----------------------------------------------------------------
# Boundary / edge-case validation
# -----------------------------------------------------------------


class TestVoiceStudioValidation:
    """Additional edge-case tests for validation rules."""

    def test_text_exactly_2000_chars_is_valid(self, vs_client):
        """Text of exactly 2000 characters should be accepted."""
        mock_provider = _fake_provider()

        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.get_tts_provider.return_value = mock_provider

            response = vs_client.post(
                "/api/voice_studio/generate",
                json={"text": "A" * 2000, "voice_id": "default"},
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

    def test_speed_at_boundaries(self, vs_client):
        """Speed at exact boundary values should be accepted."""
        mock_provider = _fake_provider()

        for speed_val in [0.7, 1.5]:
            with patch("app.voice_studio.shared") as mock_shared:
                mock_shared.custom_voices = {}
                mock_shared.get_tts_provider.return_value = mock_provider

                response = vs_client.post(
                    "/api/voice_studio/generate",
                    json={
                        "text": "Test",
                        "voice_id": "default",
                        "speed": speed_val,
                    },
                    content_type="application/json",
                )
            assert response.status_code == 200

    def test_pitch_at_boundaries(self, vs_client):
        """Pitch at exact boundary values should be accepted."""
        mock_provider = _fake_provider()

        for pitch_val in [-5, 5]:
            with patch("app.voice_studio.shared") as mock_shared:
                mock_shared.custom_voices = {}
                mock_shared.get_tts_provider.return_value = mock_provider

                response = vs_client.post(
                    "/api/voice_studio/generate",
                    json={
                        "text": "Test",
                        "voice_id": "default",
                        "pitch": pitch_val,
                    },
                    content_type="application/json",
                )
            assert response.status_code == 200


# -----------------------------------------------------------------
# POST /api/voice_clone
# -----------------------------------------------------------------


class TestVoiceCloneCreate:
    """Test POST /api/voice_clone endpoint."""

    def test_create_voice_clone_without_audio(self, vs_client):
        """Should create a voice clone entry without audio file."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.VOICE_CLONES_DIR = "/tmp/test_voice_clones"
            mock_shared.VOICE_CLONES_FILE = "/tmp/test_voice_clones/voice_clones.json"
            mock_shared.get_tts_provider.return_value = None

            import os
            os.makedirs("/tmp/test_voice_clones", exist_ok=True)

            response = vs_client.post(
                "/api/voice_clone",
                data={"voice_id": "TestVoice", "gender": "female"},
                content_type="multipart/form-data",
            )

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert data["voice_id"] == "TestVoice"

    def test_create_voice_clone_missing_name(self, vs_client):
        """Should return 400 when no voice name is provided."""
        response = vs_client.post(
            "/api/voice_clone",
            data={"language": "en"},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        data = response.json
        assert data["success"] is False

    def test_create_voice_clone_with_gender(self, vs_client):
        """Gender should be saved when creating a voice clone."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.VOICE_CLONES_DIR = "/tmp/test_vc_gender"
            mock_shared.VOICE_CLONES_FILE = "/tmp/test_vc_gender/voice_clones.json"
            mock_shared.get_tts_provider.return_value = None

            import os
            os.makedirs("/tmp/test_vc_gender", exist_ok=True)

            response = vs_client.post(
                "/api/voice_clone",
                data={"voice_id": "MaleVoice", "gender": "male"},
                content_type="multipart/form-data",
            )

        assert response.status_code == 200
        assert mock_shared.custom_voices["MaleVoice"]["gender"] == "male"

    def test_create_voice_clone_invalid_gender_defaults_to_neutral(self, vs_client):
        """Invalid gender should default to neutral."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {}
            mock_shared.VOICE_CLONES_DIR = "/tmp/test_vc_neutral"
            mock_shared.VOICE_CLONES_FILE = "/tmp/test_vc_neutral/voice_clones.json"
            mock_shared.get_tts_provider.return_value = None

            import os
            os.makedirs("/tmp/test_vc_neutral", exist_ok=True)

            response = vs_client.post(
                "/api/voice_clone",
                data={"voice_id": "BadGender", "gender": "invalid"},
                content_type="multipart/form-data",
            )

        assert response.status_code == 200
        assert mock_shared.custom_voices["BadGender"]["gender"] == "neutral"


# -----------------------------------------------------------------
# Voice Studio voices include cloned voices
# -----------------------------------------------------------------


class TestVoiceStudioIncludesClonedVoices:
    """Verify cloned voices appear in the Voice Studio dropdown."""

    def test_cloned_voices_in_voice_studio_dropdown(self, vs_client):
        """Cloned voices should appear in /api/voice_studio/voices."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {
                "alice_clone": {"gender": "female", "voice_clone_id": "alice_clone"},
                "bob_clone": {"gender": "male", "voice_clone_id": "bob_clone"},
            }
            mock_shared.get_tts_provider.return_value = None

            response = vs_client.get("/api/voice_studio/voices")

        data = response.json
        assert data["success"] is True
        ids = [v["id"] for v in data["voices"]]
        assert "alice_clone" in ids
        assert "bob_clone" in ids

    def test_cloned_voice_gender_in_dropdown(self, vs_client):
        """Cloned voice gender should be reflected in the dropdown."""
        with patch("app.voice_studio.shared") as mock_shared:
            mock_shared.custom_voices = {
                "female_voice": {"gender": "female", "voice_clone_id": "female_voice"},
            }
            mock_shared.get_tts_provider.return_value = None

            response = vs_client.get("/api/voice_studio/voices")

        data = response.json
        fv = next(v for v in data["voices"] if v["id"] == "female_voice")
        assert fv["gender"] == "female"
