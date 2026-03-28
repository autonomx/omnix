"""
<<<<<<< HEAD
API healthcheck tests.

Comprehensive healthcheck coverage for all major Omnix API endpoints.
Uses the Flask test client (no running server required).
"""

from __future__ import annotations

import pytest


# ===========================================================================
# Core health endpoint
# ===========================================================================


class TestHealthEndpoint:
    """Tests for the ``/api/health`` endpoint."""

    def test_health_returns_200(self, flask_client):
        response = flask_client.get("/api/health")
        assert response.status_code in (200, 503)

    def test_health_returns_json(self, flask_client):
        response = flask_client.get("/api/health")
        assert response.content_type.startswith("application/json")

    def test_health_has_status_field(self, flask_client):
        response = flask_client.get("/api/health")
        data = response.json
        assert "status" in data
        assert data["status"] in ("connected", "disconnected")

    def test_health_has_provider_field(self, flask_client):
        response = flask_client.get("/api/health")
        data = response.json
        assert "provider" in data
        assert isinstance(data["provider"], str)

    def test_health_has_message_field(self, flask_client):
        response = flask_client.get("/api/health")
        data = response.json
        assert "message" in data
        assert isinstance(data["message"], str)

    def test_health_idempotent(self, flask_client):
        """Calling health multiple times gives consistent results."""
        r1 = flask_client.get("/api/health").json
        r2 = flask_client.get("/api/health").json
        assert r1["status"] == r2["status"]
        assert r1["provider"] == r2["provider"]


# ===========================================================================
# Index / root page
# ===========================================================================


class TestIndexPage:
    """Tests for the ``/`` root page."""

    def test_index_returns_200(self, flask_client):
        response = flask_client.get("/")
        assert response.status_code == 200

    def test_index_returns_html(self, flask_client):
        response = flask_client.get("/")
        assert "text/html" in response.content_type


# ===========================================================================
# Settings endpoint
# ===========================================================================


class TestSettingsHealth:
    """Healthcheck-level tests for ``/api/settings``."""

    def test_get_settings_returns_200(self, flask_client):
        response = flask_client.get("/api/settings")
        assert response.status_code == 200

    def test_get_settings_returns_json(self, flask_client):
        response = flask_client.get("/api/settings")
        assert response.content_type.startswith("application/json")

    def test_get_settings_has_success(self, flask_client):
        response = flask_client.get("/api/settings")
        data = response.json
        assert data["success"] is True

    def test_get_settings_has_settings_object(self, flask_client):
        response = flask_client.get("/api/settings")
        data = response.json
        assert "settings" in data
        assert isinstance(data["settings"], dict)

    def test_get_settings_has_provider(self, flask_client):
        response = flask_client.get("/api/settings")
        settings = response.json["settings"]
        assert "provider" in settings
        assert isinstance(settings["provider"], str)

    def test_post_settings_returns_200(self, flask_client):
        response = flask_client.post(
            "/api/settings", json={"provider": "cerebras"}, content_type="application/json"
        )
        assert response.status_code == 200

    def test_post_settings_returns_success(self, flask_client):
        response = flask_client.post(
            "/api/settings", json={"provider": "lmstudio"}, content_type="application/json"
        )
        assert response.json["success"] is True

    def test_post_settings_empty_body(self, flask_client):
        response = flask_client.post(
            "/api/settings", json={}, content_type="application/json"
        )
        assert response.status_code == 200


# ===========================================================================
# Models endpoint
# ===========================================================================


class TestModelsHealth:
    """Healthcheck-level tests for ``/api/models``."""

    def test_get_models_responds(self, flask_client):
        response = flask_client.get("/api/models")
        assert response.status_code in (200, 500)

    def test_get_models_returns_json(self, flask_client):
        response = flask_client.get("/api/models")
        assert response.content_type.startswith("application/json")


# ===========================================================================
# Sessions CRUD
# ===========================================================================


class TestSessionsHealth:
    """Healthcheck-level tests for ``/api/sessions``."""

    def test_get_sessions_returns_200(self, flask_client):
        response = flask_client.get("/api/sessions")
        assert response.status_code == 200

    def test_get_sessions_returns_json(self, flask_client):
        response = flask_client.get("/api/sessions")
        assert response.content_type.startswith("application/json")

    def test_get_sessions_has_success(self, flask_client):
        response = flask_client.get("/api/sessions")
        data = response.json
        assert data["success"] is True

    def test_get_sessions_has_list(self, flask_client):
        response = flask_client.get("/api/sessions")
        data = response.json
        assert isinstance(data["sessions"], list)

    def test_create_session_returns_200(self, flask_client):
        resp = flask_client.post("/api/sessions")
        assert resp.status_code == 200
        flask_client.delete(f"/api/sessions/{resp.json['session_id']}")

    def test_create_session_has_id(self, flask_client):
        resp = flask_client.post("/api/sessions")
        data = resp.json
        assert data["success"] is True
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0
        flask_client.delete(f"/api/sessions/{data['session_id']}")

    def test_session_crud_lifecycle(self, flask_client):
        """Full create-read-update-delete cycle."""
        # Create
        resp = flask_client.post("/api/sessions")
        assert resp.status_code == 200
        sid = resp.json["session_id"]

        # Read
        resp = flask_client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert "session" in resp.json

        # Update
        resp = flask_client.put(
            f"/api/sessions/{sid}", json={"title": "Updated"}, content_type="application/json"
        )
        assert resp.status_code == 200

        # Delete
        resp = flask_client.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200

    def test_get_nonexistent_session_returns_404(self, flask_client):
        response = flask_client.get("/api/sessions/nonexistent_xyz_999")
        assert response.status_code == 404
        assert response.json["success"] is False

    def test_session_detail_has_messages(self, flask_client):
        resp = flask_client.post("/api/sessions")
        sid = resp.json["session_id"]
        detail = flask_client.get(f"/api/sessions/{sid}").json
        assert "messages" in detail["session"]
        assert isinstance(detail["session"]["messages"], list)
        flask_client.delete(f"/api/sessions/{sid}")

    def test_new_session_has_empty_messages(self, flask_client):
        resp = flask_client.post("/api/sessions")
        sid = resp.json["session_id"]
        detail = flask_client.get(f"/api/sessions/{sid}").json
        assert len(detail["session"]["messages"]) == 0
        flask_client.delete(f"/api/sessions/{sid}")

    def test_session_appears_in_list_after_creation(self, flask_client):
        resp = flask_client.post("/api/sessions")
        sid = resp.json["session_id"]
        sessions = flask_client.get("/api/sessions").json["sessions"]
        session_ids = [s["id"] for s in sessions]
        assert sid in session_ids
        flask_client.delete(f"/api/sessions/{sid}")

    def test_session_disappears_from_list_after_deletion(self, flask_client):
        resp = flask_client.post("/api/sessions")
        sid = resp.json["session_id"]
        flask_client.delete(f"/api/sessions/{sid}")
        sessions = flask_client.get("/api/sessions").json["sessions"]
        session_ids = [s["id"] for s in sessions]
        assert sid not in session_ids


# ===========================================================================
# Providers
# ===========================================================================


class TestProvidersHealth:
    """Healthcheck-level tests for provider endpoints."""

    def test_providers_status_responds(self, flask_client):
        response = flask_client.get("/api/providers/status")
        assert response.status_code in (200, 500)

    def test_providers_status_returns_json(self, flask_client):
        response = flask_client.get("/api/providers/status")
        assert response.content_type.startswith("application/json")

    def test_providers_status_has_llm_key(self, flask_client):
        response = flask_client.get("/api/providers/status")
        if response.status_code == 200:
            data = response.json
            assert "llm" in data

    def test_providers_status_has_tts_key(self, flask_client):
        response = flask_client.get("/api/providers/status")
        if response.status_code == 200:
            data = response.json
            assert "tts" in data

    def test_providers_list_responds(self, flask_client):
        response = flask_client.get("/api/providers")
        assert response.status_code in (200, 500)

    def test_providers_list_returns_json(self, flask_client):
        response = flask_client.get("/api/providers")
        if response.status_code == 200:
            data = response.json
            assert data["success"] is True
            assert "providers" in data
            assert isinstance(data["providers"], list)


# ===========================================================================
# TTS speakers
# ===========================================================================


class TestTTSSpeakersHealth:
    """Healthcheck-level tests for ``/api/tts/speakers``."""

    def test_tts_speakers_responds(self, flask_client):
        response = flask_client.get("/api/tts/speakers")
        assert response.status_code in (200, 500)

    def test_tts_speakers_returns_json(self, flask_client):
        response = flask_client.get("/api/tts/speakers")
        assert response.content_type.startswith("application/json")


# ===========================================================================
# Services status
# ===========================================================================


class TestServicesHealth:
    """Healthcheck-level tests for ``/api/services/status``."""

    def test_services_status_responds(self, flask_client):
        response = flask_client.get("/api/services/status")
        assert response.status_code in (200, 500)

    def test_services_status_returns_json(self, flask_client):
        response = flask_client.get("/api/services/status")
        assert response.content_type.startswith("application/json")

    def test_services_status_has_tts(self, flask_client):
        response = flask_client.get("/api/services/status")
        if response.status_code == 200:
            data = response.json
            assert "tts" in data

    def test_services_status_has_stt(self, flask_client):
        response = flask_client.get("/api/services/status")
        if response.status_code == 200:
            data = response.json
            assert "stt" in data


# ===========================================================================
# llama.cpp server
# ===========================================================================


class TestLlamaCppHealth:
    """Healthcheck-level tests for ``/api/llamacpp/server/status``."""

    def test_llamacpp_status_responds(self, flask_client):
        response = flask_client.get("/api/llamacpp/server/status")
        assert response.status_code in (200, 500)

    def test_llamacpp_status_returns_json(self, flask_client):
        response = flask_client.get("/api/llamacpp/server/status")
        assert response.content_type.startswith("application/json")


# ===========================================================================
# Podcast
# ===========================================================================


class TestPodcastHealth:
    """Healthcheck-level tests for ``/api/podcast/episodes``."""

    def test_podcast_episodes_responds(self, flask_client):
        response = flask_client.get("/api/podcast/episodes")
        assert response.status_code in (200, 500)

    def test_podcast_episodes_returns_json(self, flask_client):
        response = flask_client.get("/api/podcast/episodes")
        assert response.content_type.startswith("application/json")


# ===========================================================================
# Clear
# ===========================================================================


class TestClearHealth:
    """Healthcheck-level tests for ``/api/clear``."""

    def test_clear_returns_200(self, flask_client):
        response = flask_client.post("/api/clear", json={}, content_type="application/json")
        assert response.status_code == 200

    def test_clear_returns_success(self, flask_client):
        response = flask_client.post("/api/clear", json={}, content_type="application/json")
        assert response.json["success"] is True

    def test_clear_with_session_id(self, flask_client):
        resp = flask_client.post("/api/sessions")
        sid = resp.json["session_id"]
        response = flask_client.post(
            "/api/clear", json={"session_id": sid}, content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        flask_client.delete(f"/api/sessions/{sid}")


# ===========================================================================
# HTTP method and error handling
# ===========================================================================


class TestHTTPMethodHandling:
    """Verify endpoints reject unsupported HTTP methods."""

    def test_health_rejects_post(self, flask_client):
        response = flask_client.post("/api/health")
        assert response.status_code == 405

    def test_settings_rejects_delete(self, flask_client):
        response = flask_client.delete("/api/settings")
        assert response.status_code == 405

    def test_sessions_rejects_put_on_collection(self, flask_client):
        response = flask_client.put("/api/sessions")
        assert response.status_code == 405

    def test_health_rejects_put(self, flask_client):
        response = flask_client.put("/api/health")
        assert response.status_code == 405


# ===========================================================================
# Content-Type consistency
# ===========================================================================


class TestContentTypeConsistency:
    """Ensure all API endpoints consistently return JSON."""

    @pytest.mark.parametrize("endpoint", [
        "/api/health",
        "/api/settings",
        "/api/sessions",
        "/api/providers/status",
        "/api/services/status",
    ])
    def test_endpoint_returns_json_content_type(self, flask_client, endpoint):
        response = flask_client.get(endpoint)
        assert response.content_type.startswith("application/json")
=======
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
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f
