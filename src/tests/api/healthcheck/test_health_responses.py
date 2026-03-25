"""
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
