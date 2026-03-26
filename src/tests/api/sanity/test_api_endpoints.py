"""
API endpoint tests – migrated from test_api_endpoints.py.

These tests use the Flask test client (no running server needed) to verify
HTTP routes respond correctly.
"""

from __future__ import annotations

import json
import base64
import pytest
from unittest.mock import patch, MagicMock


# ===========================================================================
# Health
# ===========================================================================


class TestHealthEndpoint:
    """Health check endpoint."""

    def test_health_endpoint_responds(self, flask_client):
        response = flask_client.get("/api/health")
        assert response.status_code in (200, 503)


# ===========================================================================
# Settings
# ===========================================================================


class TestSettingsEndpoints:
    """Settings CRUD."""

    def test_get_settings(self, flask_client):
        response = flask_client.get("/api/settings")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "settings" in data

    def test_save_settings(self, flask_client):
        new_settings = {"provider": "lmstudio", "lmstudio": {"base_url": "http://localhost:1234"}}
        response = flask_client.post(
            "/api/settings", json=new_settings, content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json["success"] is True


# ===========================================================================
# Sessions
# ===========================================================================


class TestSessionEndpoints:
    """Session management."""

    def test_get_sessions(self, flask_client):
        response = flask_client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert isinstance(data["sessions"], list)

    def test_create_session(self, flask_client):
        response = flask_client.post("/api/sessions")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "session_id" in data
        flask_client.delete(f"/api/sessions/{data['session_id']}")

    def test_get_session(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        response = flask_client.get(f"/api/sessions/{sid}")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert "session" in response.json
        flask_client.delete(f"/api/sessions/{sid}")

    def test_delete_session(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        response = flask_client.delete(f"/api/sessions/{sid}")
        assert response.status_code == 200

    def test_get_nonexistent_session_returns_404(self, flask_client):
        response = flask_client.get("/api/sessions/nonexistent_id_xyz")
        assert response.status_code == 404
