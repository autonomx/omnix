"""
API healthcheck tests – migrated from healthcheck/test_endpoints.py.

These tests use Playwright's ``APIRequestContext`` to call endpoints on a
running server (or fall back to the Flask test client).
"""

from __future__ import annotations

import pytest


class TestHealthcheckFlask:
    """Healthcheck tests using the Flask test client (no running server required)."""

    # -- Core --

    def test_index_page(self, flask_client):
        response = flask_client.get("/")
        assert response.status_code == 200

    def test_health(self, flask_client):
        response = flask_client.get("/api/health")
        assert response.status_code in (200, 503)

    # -- Settings --

    def test_get_settings(self, flask_client):
        response = flask_client.get("/api/settings")
        assert response.status_code == 200

    def test_post_settings(self, flask_client):
        response = flask_client.post(
            "/api/settings", json={"provider": "cerebras"}, content_type="application/json"
        )
        assert response.status_code == 200

    # -- Models --

    def test_get_models(self, flask_client):
        response = flask_client.get("/api/models")
        assert response.status_code in (200, 500)

    # -- Sessions CRUD --

    def test_session_crud(self, flask_client):
        # Create
        resp = flask_client.post("/api/sessions")
        assert resp.status_code == 200
        sid = resp.json.get("session_id")
        assert sid

        # Read
        resp = flask_client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200

        # Update
        resp = flask_client.put(
            f"/api/sessions/{sid}", json={"title": "Test"}, content_type="application/json"
        )
        assert resp.status_code == 200

        # Delete
        resp = flask_client.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200

    # -- TTS --

    def test_tts_speakers(self, flask_client):
        response = flask_client.get("/api/tts/speakers")
        assert response.status_code in (200, 500)

    # -- Providers --

    def test_providers_status(self, flask_client):
        response = flask_client.get("/api/providers/status")
        assert response.status_code in (200, 500)

    # -- llama.cpp --

    def test_llamacpp_server_status(self, flask_client):
        response = flask_client.get("/api/llamacpp/server/status")
        assert response.status_code in (200, 500)

    # -- Podcast --

    def test_podcast_episodes(self, flask_client):
        response = flask_client.get("/api/podcast/episodes")
        assert response.status_code in (200, 500)

    # -- Services --

    def test_services_status(self, flask_client):
        response = flask_client.get("/api/services/status")
        assert response.status_code in (200, 500)

    # -- Clear --

    def test_clear(self, flask_client):
        response = flask_client.post("/api/clear", json={}, content_type="application/json")
        assert response.status_code == 200
