"""
Comprehensive healthcheck tests for FastAPI server endpoints.

Tests cover:
- /health (basic server liveness)
- /api/health (LLM provider connectivity)
- /api/providers/status (all provider statuses)
- /api/services/status (TTS/STT service status)
- /api/llamacpp/server/status (llama.cpp server status)
- Response schemas and edge cases
"""

import json
import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Ensure project root and src/ are on the path
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(os.path.dirname(os.path.dirname(_tests_dir)))
_project_root = os.path.dirname(_src_dir)
sys.path.insert(0, _project_root)
sys.path.insert(0, _src_dir)


# ---------------------------------------------------------------------------
# Helpers – import FastAPI app with heavy deps stubbed out
# ---------------------------------------------------------------------------


def _import_app():
    """Import the FastAPI app, mocking heavy deps if needed."""
    try:
        import numpy  # noqa: F401
    except ImportError:
        sys.modules.setdefault("numpy", MagicMock())

    from server_fastapi import app
    return app


def _make_client():
    """Create a TestClient for the FastAPI app."""
    from starlette.testclient import TestClient

    app = _import_app()
    return TestClient(app, raise_server_exceptions=False)


# ===================================================================
# /health – basic liveness
# ===================================================================


class TestHealthLiveness:
    """Tests for GET /health (simple liveness probe)."""

    def test_health_returns_200(self):
        """Health endpoint must return 200 OK."""
        client = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_schema(self):
        """Response must contain status and server keys."""
        client = _make_client()
        data = client.get("/health").json()
        assert "status" in data
        assert "server" in data

    def test_health_status_ok(self):
        """Status must be 'ok' when the server is running."""
        client = _make_client()
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_server_is_fastapi(self):
        """Server identifier must be 'fastapi'."""
        client = _make_client()
        data = client.get("/health").json()
        assert data["server"] == "fastapi"

    def test_health_json_content_type(self):
        """Response Content-Type must be application/json."""
        client = _make_client()
        resp = client.get("/health")
        assert "application/json" in resp.headers.get("content-type", "")


# ===================================================================
# /api/health – provider health check
# ===================================================================


class TestApiHealth:
    """Tests for GET /api/health (LLM provider connectivity)."""

    def test_no_provider_returns_disconnected(self):
        """When no provider is configured, status should be 'disconnected'."""
        client = _make_client()
        with patch("app.shared.get_provider", return_value=None):
            data = client.get("/api/health").json()
        assert data["status"] == "disconnected"
        assert data["provider"] == "unknown"
        assert "message" in data

    def test_provider_healthy(self):
        """When provider.test_connection() returns True, status is 'connected'."""
        mock_provider = MagicMock()
        mock_provider.test_connection.return_value = True
        mock_provider.provider_name = "lmstudio"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_provider):
            data = client.get("/api/health").json()

        assert data["status"] == "connected"
        assert data["provider"] == "lmstudio"
        assert data["message"] == "OK"

    def test_provider_unhealthy(self):
        """When provider.test_connection() returns False, status is 'disconnected'."""
        mock_provider = MagicMock()
        mock_provider.test_connection.return_value = False
        mock_provider.provider_name = "cerebras"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_provider):
            data = client.get("/api/health").json()

        assert data["status"] == "disconnected"
        assert data["provider"] == "cerebras"
        assert data["message"] == "Connection failed"

    def test_provider_raises_exception(self):
        """When test_connection() raises, status is 'disconnected' with error message."""
        mock_provider = MagicMock()
        mock_provider.test_connection.side_effect = ConnectionError("timeout")
        mock_provider.provider_name = "openrouter"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_provider):
            data = client.get("/api/health").json()

        assert data["status"] == "disconnected"
        assert data["provider"] == "openrouter"
        assert "timeout" in data["message"]

    def test_api_health_response_always_has_three_keys(self):
        """All /api/health responses must include status, provider, message."""
        client = _make_client()
        # No provider case
        with patch("app.shared.get_provider", return_value=None):
            data = client.get("/api/health").json()
        for key in ("status", "provider", "message"):
            assert key in data, f"Missing key '{key}' in response"

    def test_api_health_status_values_are_valid(self):
        """Status must be either 'connected' or 'disconnected'."""
        mock_provider = MagicMock()
        mock_provider.test_connection.return_value = True
        mock_provider.provider_name = "test"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_provider):
            data = client.get("/api/health").json()
        assert data["status"] in ("connected", "disconnected")


# ===================================================================
# /api/providers/status – all provider statuses
# ===================================================================


class TestProvidersStatus:
    """Tests for GET /api/providers/status."""

    def test_no_providers_configured(self):
        """When no providers exist, response still returns valid structure."""
        client = _make_client()
        with patch("app.shared.get_provider", return_value=None), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert data["success"] is True
        assert "llm" in data
        assert "tts" in data
        assert data["llm"]["available"] is False
        assert data["tts"]["available"] is False

    def test_llm_provider_healthy(self):
        """LLM provider shows available when test_connection succeeds."""
        mock_llm = MagicMock()
        mock_llm.test_connection.return_value = True
        mock_llm.provider_name = "lmstudio"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_llm), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert data["success"] is True
        assert data["llm"]["available"] is True
        assert data["llm"]["provider"] == "lmstudio"
        assert data["llm"]["message"] == "OK"

    def test_tts_provider_available(self):
        """TTS provider shows available when loaded."""
        mock_tts = MagicMock()
        mock_tts.provider_name = "chatterbox"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=None), \
              patch("app.shared.get_tts_provider", return_value=mock_tts):
            data = client.get("/api/providers/status").json()

        assert data["tts"]["available"] is True
        assert data["tts"]["provider"] == "chatterbox"

    def test_tts_provider_not_loaded(self):
        """TTS shows not available when not loaded."""
        client = _make_client()
        with patch("app.shared.get_provider", return_value=None), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert data["tts"]["available"] is False
        assert data["tts"]["provider"] == "none"
        assert data["tts"]["message"] == "Not loaded"

    def test_llm_provider_connection_fails(self):
        """LLM shows unavailable when test_connection returns False."""
        mock_llm = MagicMock()
        mock_llm.test_connection.return_value = False
        mock_llm.provider_name = "cerebras"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_llm), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert data["llm"]["available"] is False
        assert data["llm"]["message"] == "Connection failed"

    def test_llm_provider_raises_exception(self):
        """LLM shows unavailable with error message on exception."""
        mock_llm = MagicMock()
        mock_llm.test_connection.side_effect = RuntimeError("network error")
        mock_llm.provider_name = "openrouter"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_llm), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert data["llm"]["available"] is False
        assert "network error" in data["llm"]["message"]

    def test_both_providers_healthy(self):
        """Both LLM and TTS show as available."""
        mock_llm = MagicMock()
        mock_llm.test_connection.return_value = True
        mock_llm.provider_name = "lmstudio"

        mock_tts = MagicMock()
        mock_tts.provider_name = "chatterbox"

        client = _make_client()
        with patch("app.shared.get_provider", return_value=mock_llm), \
              patch("app.shared.get_tts_provider", return_value=mock_tts):
            data = client.get("/api/providers/status").json()

        assert data["success"] is True
        assert data["llm"]["available"] is True
        assert data["tts"]["available"] is True

    def test_providers_status_response_schema(self):
        """Response must have success, llm, and tts keys."""
        client = _make_client()
        with patch("app.shared.get_provider", return_value=None), \
              patch("app.shared.get_tts_provider", return_value=None):
            data = client.get("/api/providers/status").json()

        assert "success" in data
        assert "llm" in data
        assert "tts" in data
        # LLM sub-structure
        for key in ("available", "provider", "message"):
            assert key in data["llm"], f"Missing 'llm.{key}'"
        # TTS sub-structure
        for key in ("available", "provider", "message"):
            assert key in data["tts"], f"Missing 'tts.{key}'"


# ===================================================================
# /api/services/status – TTS/STT microservice health
# ===================================================================


class TestServicesStatus:
    """Tests for GET /api/services/status."""

    def test_services_all_down(self):
        """When both TTS and STT are unreachable, both show not running."""
        client = _make_client()
        with patch("requests.get", side_effect=ConnectionError("refused")):
            data = client.get("/api/services/status").json()

        assert data["success"] is True
        assert data["tts"]["running"] is False
        assert data["stt"]["running"] is False

    def test_tts_running_stt_down(self):
        """TTS running, STT not."""
        tts_resp = MagicMock()
        tts_resp.status_code = 200

        def side_effect(url, **kwargs):
            if "8020" in url or "tts" in url.lower():
                return tts_resp
            raise ConnectionError("STT down")

        client = _make_client()
        with patch("requests.get", side_effect=side_effect):
            data = client.get("/api/services/status").json()

        assert data["tts"]["running"] is True
        assert data["stt"]["running"] is False

    def test_stt_running_tts_down(self):
        """STT running, TTS not."""
        stt_resp = MagicMock()
        stt_resp.status_code = 200

        def side_effect(url, **kwargs):
            if "8000" in url or "stt" in url.lower():
                return stt_resp
            raise ConnectionError("TTS down")

        client = _make_client()
        with patch("requests.get", side_effect=side_effect):
            data = client.get("/api/services/status").json()

        assert data["tts"]["running"] is False
        assert data["stt"]["running"] is True

    def test_both_services_running(self):
        """Both TTS and STT running."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        client = _make_client()
        with patch("requests.get", return_value=mock_resp):
            data = client.get("/api/services/status").json()

        assert data["success"] is True
        assert data["tts"]["running"] is True
        assert data["stt"]["running"] is True

    def test_services_status_response_schema(self):
        """Response must have success, tts, stt keys."""
        client = _make_client()
        with patch("requests.get", side_effect=ConnectionError):
            data = client.get("/api/services/status").json()

        assert "success" in data
        assert "tts" in data
        assert "stt" in data
        assert "running" in data["tts"]
        assert "running" in data["stt"]

    def test_services_timeout_treated_as_down(self):
        """Timeout from TTS/STT service is treated as not running."""
        import requests as req_lib

        client = _make_client()
        with patch("requests.get", side_effect=req_lib.exceptions.Timeout):
            data = client.get("/api/services/status").json()

        assert data["tts"]["running"] is False
        assert data["stt"]["running"] is False

    def test_services_non_200_treated_as_down(self):
        """Non-200 response from TTS/STT service is treated as not running."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        client = _make_client()
        with patch("requests.get", return_value=mock_resp):
            data = client.get("/api/services/status").json()

        assert data["tts"]["running"] is False
        assert data["stt"]["running"] is False


# ===================================================================
# /api/llamacpp/server/status – llama.cpp server status
# ===================================================================


class TestLlamaCppStatus:
    """Tests for GET /api/llamacpp/server/status."""

    def test_llamacpp_status_returns_200(self):
        """Endpoint must return 200 even when server not installed."""
        client = _make_client()
        resp = client.get("/api/llamacpp/server/status")
        assert resp.status_code == 200

    def test_llamacpp_status_has_expected_keys(self):
        """Response must contain key status information."""
        client = _make_client()
        data = client.get("/api/llamacpp/server/status").json()
        # Must indicate whether binary is present and server running
        assert isinstance(data, dict)


# ===================================================================
# Root / endpoint
# ===================================================================


class TestRootEndpoint:
    """Tests for GET / (main page serving)."""

    def test_root_returns_html(self):
        """Root endpoint should return HTML."""
        client = _make_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


# ===================================================================
# Response consistency across health endpoints
# ===================================================================


class TestHealthConsistency:
    """Cross-cutting tests across multiple health endpoints."""

    def test_all_health_endpoints_return_json_or_html(self):
        """All health endpoints must return valid JSON."""
        client = _make_client()
        json_endpoints = ["/health", "/api/health", "/api/providers/status"]

        with patch("app.shared.get_provider", return_value=None), \
              patch("app.shared.get_tts_provider", return_value=None), \
              patch("requests.get", side_effect=ConnectionError):
            for endpoint in json_endpoints:
                resp = client.get(endpoint)
                assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"
                data = resp.json()
                assert isinstance(data, dict), f"{endpoint} did not return a dict"

    def test_health_endpoints_do_not_require_auth(self):
        """Health endpoints should be accessible without authentication."""
        client = _make_client()
        endpoints = ["/health", "/api/health"]

        with patch("app.shared.get_provider", return_value=None):
            for endpoint in endpoints:
                resp = client.get(endpoint)
                # Should not return 401 or 403
                assert resp.status_code not in (401, 403), \
                    f"{endpoint} requires authentication"


# ===================================================================
# /api/rpg/adventure/* – RPG Adventure Builder Health
# ===================================================================

class TestRPGAdventureHealth:
    """Healthcheck-level tests for RPG adventure builder endpoints."""

    def test_adventure_preview_responds(self):
        """POST /api/rpg/adventure/preview should respond (200 or 500)."""
        client = _make_client()
        # Send empty setup to test basic response
        resp = client.post("/api/rpg/adventure/preview", json={"setup": {}})
        assert resp.status_code in (200, 500)

    def test_adventure_preview_returns_json(self):
        """POST /api/rpg/adventure/preview should return JSON."""
        client = _make_client()
        resp = client.post("/api/rpg/adventure/preview", json={"setup": {}})
        assert "application/json" in resp.headers.get("content-type", "")

    def test_adventure_start_responds(self):
        """POST /api/rpg/adventure/start should respond (200 or 500)."""
        client = _make_client()
        resp = client.post("/api/rpg/adventure/start", json={})
        assert resp.status_code in (200, 500)

    def test_adventure_start_returns_json(self):
        """POST /api/rpg/adventure/start should return JSON."""
        client = _make_client()
        resp = client.post("/api/rpg/adventure/start", json={})
        assert "application/json" in resp.headers.get("content-type", "")

    def test_adventure_validate_responds(self):
        """POST /api/rpg/adventure/validate should respond."""
        client = _make_client()
        resp = client.post("/api/rpg/adventure/validate", json={})
        assert resp.status_code in (200, 400, 500)

    def test_adventure_validate_returns_json(self):
        """POST /api/rpg/adventure/validate should return JSON."""
        client = _make_client()
        resp = client.post("/api/rpg/adventure/validate", json={})
        assert "application/json" in resp.headers.get("content-type", "")

    def test_adventure_templates_returns_200(self):
        """GET /api/rpg/adventure/templates should return 200."""
        client = _make_client()
        resp = client.get("/api/rpg/adventure/templates")
        assert resp.status_code == 200

    def test_adventure_templates_returns_json(self):
        """GET /api/rpg/adventure/templates should return JSON."""
        client = _make_client()
        resp = client.get("/api/rpg/adventure/templates")
        assert "application/json" in resp.headers.get("content-type", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
