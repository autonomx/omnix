"""
TTS Service sanity tests.

These tests run against running services to verify that the TTS HTTP
architecture is working correctly after the migration from local provider
to separate TTS service.

Tests both the TTS backend service (port 5101) and the frontend API proxy (port 5000).
"""

from __future__ import annotations

import pytest
import requests
from typing import Dict, Any


# Test configuration
TTS_SERVICE_BASE = "http://127.0.0.1:5101"
MAIN_API_BASE = "http://127.0.0.1:5000"


def is_service_running(url: str, timeout: float = 2.0) -> bool:
    """Helper to check if a service is reachable."""
    try:
        requests.get(url, timeout=timeout)
        return True
    except requests.exceptions.ConnectionError:
        return False


def _pick_test_speaker() -> str:
    """
    Resolve a speaker dynamically from the live TTS service so this test does not
    become brittle if the built-in default set changes.
    """
    response = requests.get(f"{TTS_SERVICE_BASE}/api/tts/speakers", timeout=5)
    response.raise_for_status()
    data = response.json()
    speakers = data.get("speakers") or []
    assert speakers, f"No speakers returned from TTS service: {data}"

    preferred_ids = ("Maya", "maya")
    for speaker in speakers:
        speaker_id = str(speaker.get("id") or "")
        if speaker_id in preferred_ids:
            return speaker_id

    return str(speakers[0]["id"])


def _assert_no_known_tts_loader_failure(text: str) -> None:
    """
    Guardrail for the exact failure modes seen in production logs.
    We intentionally check response text for these signatures because
    one route can falsely appear 'successful' while another is actually
    failing underneath.
    """
    lowered = (text or "").lower()
    forbidden_fragments = [
        "model loading failed",
        "failed to load vendored qwen3-tts model",
        "failed to load fasterqwen3tts model",
        "nonetype' object has no attribute 'get'",
        "incompatible safetensors file",
        "file metadata is not ['pt', 'tf', 'flax', 'mlx'] but none",
        "falling back to reference preview audio",
        "reference preview audio",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in lowered, (
            f"TTS response leaked known loader/fallback failure fragment: {fragment!r}\n"
            f"Response text:\n{text}"
        )


@pytest.fixture(scope="module")
def tts_service_available() -> bool:
    """Fixture to skip tests if TTS service is not running."""
    available = is_service_running(f"{TTS_SERVICE_BASE}/health")
    if not available:
        pytest.skip("TTS service (port 5101) is not running")
    return available


@pytest.fixture(scope="module")
def main_api_available() -> bool:
    """Fixture to skip tests if main API is not running."""
    available = is_service_running(f"{MAIN_API_BASE}/api/health")
    if not available:
        pytest.skip("Main API (port 5000) is not running")
    return available


class TestTtsServiceBackend:
    """Tests for the standalone TTS service at port 5101."""

    def test_health_endpoint_responds(self, tts_service_available: bool) -> None:
        """Test /health endpoint returns valid structure."""
        response = requests.get(f"{TTS_SERVICE_BASE}/health", timeout=3)
        
        # Should always return 200 even if not ready
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        
        # Required fields
        assert "ok" in data
        assert isinstance(data["ok"], bool)
        assert "provider" in data
        assert "status" in data
        
        # Optional fields
        if data["ok"]:
            assert data["status"] == "ready"
            assert "details" in data

    def test_speakers_endpoint(self, tts_service_available: bool) -> None:
        """Test /api/tts/speakers returns speaker list."""
        response = requests.get(f"{TTS_SERVICE_BASE}/api/tts/speakers", timeout=3)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "speakers" in data
        assert isinstance(data["speakers"], list)
        assert "provider" in data
        
        # Each speaker should have id and name
        for speaker in data["speakers"]:
            assert isinstance(speaker, dict)
            assert "id" in speaker
            assert "name" in speaker
            assert speaker["id"] and speaker["name"]

    @pytest.mark.e2e
    def test_tts_server_real_generation(self, tts_service_available: bool) -> None:
        """
        FULL real path:
        HTTP → TTS server → provider → model → audio

        Requires:
        - server running on :5101
        - model actually loadable
        """

        url = f"{TTS_SERVICE_BASE}/api/tts/generate_audio"

        payload = {
            "text": "hello world",
            "speaker": "Maya",
            "language": "en"
        }

        try:
            r = requests.post(url, json=payload, timeout=30)
        except Exception as e:
            pytest.fail(f"TTS server unreachable: {e}")

        assert r.status_code == 200, r.text

        data = r.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "audio_base64" in data

    @pytest.mark.e2e
    def test_tts_server_stream_and_nonstream_are_both_real_and_consistent(
        self,
        tts_service_available: bool,
    ) -> None:
        """
        Regression guard for the split failure mode where:
        - /generate_audio returns 200 because it falls back to preview audio
        - /generate_stream_audio returns 500 due to real model load failure

        This test must fail if:
        - non-stream path only "succeeds" via fallback
        - stream path fails while non-stream path passes
        - known vendored Qwen/safetensors loader errors surface in either path
        """
        speaker = _pick_test_speaker()
        payload = {
            "text": "Sanity check. The quick brown fox jumps over the lazy dog.",
            "speaker": speaker,
            "language": "en",
        }

        nonstream_url = f"{TTS_SERVICE_BASE}/api/tts/generate_audio"
        stream_url = f"{TTS_SERVICE_BASE}/api/tts/generate_stream_audio"

        try:
            nonstream_response = requests.post(nonstream_url, json=payload, timeout=60)
        except Exception as e:
            pytest.fail(f"Non-stream TTS request failed to reach service: {e}")

        assert nonstream_response.status_code == 200, (
            f"/generate_audio returned unexpected status {nonstream_response.status_code}: "
            f"{nonstream_response.text}"
        )
        _assert_no_known_tts_loader_failure(nonstream_response.text)

        nonstream_data = nonstream_response.json()
        assert nonstream_data.get("success") is True, (
            f"/generate_audio expected success=True, got: {nonstream_data}"
        )
        assert nonstream_data.get("audio_base64"), (
            f"/generate_audio missing audio_base64: {nonstream_data}"
        )

        try:
            stream_response = requests.post(stream_url, json=payload, timeout=60)
        except Exception as e:
            pytest.fail(f"Stream TTS request failed to reach service: {e}")

        assert stream_response.status_code == 200, (
            "/generate_stream_audio failed while /generate_audio succeeded. "
            "This usually means the non-stream path masked a real provider/model "
            "failure via fallback while the stream path exercised the real load path.\n"
            f"Stream status={stream_response.status_code}\n"
            f"Stream body:\n{stream_response.text}\n"
            f"Non-stream body:\n{nonstream_response.text}"
        )
        _assert_no_known_tts_loader_failure(stream_response.text)

        content_type = (stream_response.headers.get("content-type") or "").lower()
        assert content_type, "Missing Content-Type header on /generate_stream_audio response"
        assert not content_type.startswith("application/json"), (
            "/generate_stream_audio returned JSON instead of streaming/binary audio.\n"
            f"Headers: {dict(stream_response.headers)}\n"
            f"Body:\n{stream_response.text}"
        )
        assert len(stream_response.content) > 0, "Empty body returned from /generate_stream_audio"


class TestMainApiProxy:
    """Tests for the main API at port 5000 which proxies TTS requests."""

    def test_tts_speakers_proxy(self, main_api_available: bool) -> None:
        """Test /api/tts/speakers returns speakers via proxy."""
        response = requests.get(f"{MAIN_API_BASE}/api/tts/speakers", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "speakers" in data
        assert isinstance(data["speakers"], list)
        
        # Verify structure matches TTS service format
        for speaker in data["speakers"]:
            assert "id" in speaker
            assert "name" in speaker

    def test_providers_status_includes_tts(self, main_api_available: bool) -> None:
        """Test /api/providers/status includes TTS service status."""
        response = requests.get(f"{MAIN_API_BASE}/api/providers/status", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "tts" in data
        assert isinstance(data["tts"], dict)
        
        tts_status = data["tts"]
        assert "available" in tts_status
        assert isinstance(tts_status["available"], bool)
        assert "provider" in tts_status
        assert "message" in tts_status
        
        # Should use the HTTP provider now, not local
        assert tts_status["provider"] in ("tts-http", "qwen3_tts")


class TestTtsIntegration:
    """Integration tests verifying full flow between services."""

    def test_both_services_return_same_speakers(self,
                                                tts_service_available: bool,
                                                main_api_available: bool) -> None:
        """Verify both endpoints return consistent speaker lists."""
        tts_resp = requests.get(f"{TTS_SERVICE_BASE}/api/tts/speakers", timeout=3)
        main_resp = requests.get(f"{MAIN_API_BASE}/api/tts/speakers", timeout=5)
        
        tts_data = tts_resp.json()
        main_data = main_resp.json()
        
        # Both should succeed
        assert tts_data["success"] is True
        assert main_data["success"] is True
        
        # Get speaker IDs from both
        tts_ids = {s["id"] for s in tts_data["speakers"]}
        main_ids = {s["id"] for s in main_data["speakers"]}
        
        # Should have at least the built-in speakers in common
        common = tts_ids.intersection(main_ids)
        assert len(common) >= 1, "No common speakers found between services"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])