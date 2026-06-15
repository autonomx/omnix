"""Legacy session compatibility contract tests for the gateway."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


def test_gateway_legacy_sessions_crud_contract() -> None:
    sessions: dict[str, dict] = {}

    with (
        patch("app.shared.load_sessions", side_effect=lambda: sessions),
        patch("app.shared.save_sessions", side_effect=lambda next_sessions: sessions.update(next_sessions)),
        patch("app.shared.get_global_system_prompt", return_value="System prompt"),
    ):
        create_response = _client().post("/api/sessions")
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["success"] is True
        session_id = created["session_id"]

        list_response = _client().get("/api/sessions")
        assert list_response.status_code == 200
        assert list_response.json()["sessions"][0]["id"] == session_id

        get_response = _client().get(f"/api/sessions/{session_id}")
        assert get_response.status_code == 200
        assert get_response.json()["session"]["messages"] == []
        assert get_response.json()["session"]["system_prompt"] == "System prompt"

        update_response = _client().put(
            f"/api/sessions/{session_id}",
            json={"title": "Renamed", "system_prompt": "Updated prompt"},
        )
        assert update_response.status_code == 200
        assert update_response.json() == {"success": True}
        assert sessions[session_id]["title"] == "Renamed"
        assert sessions[session_id]["system_prompt"] == "Updated prompt"

        delete_response = _client().delete(f"/api/sessions/{session_id}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"success": True}
        assert session_id not in sessions

        missing_response = _client().get(f"/api/sessions/{session_id}")
        assert missing_response.status_code == 404


def test_gateway_legacy_sessions_list_orders_newest_first() -> None:
    with patch(
        "app.shared.load_sessions",
        return_value={
            "old": {"title": "Old", "updated_at": "2026-06-14T00:00:00"},
            "new": {"title": "New", "updated_at": "2026-06-15T00:00:00"},
        },
    ):
        response = _client().get("/api/sessions")

    assert response.status_code == 200
    assert [session["id"] for session in response.json()["sessions"]] == ["new", "old"]


def test_gateway_legacy_generate_title_uses_safe_fallback_without_provider() -> None:
    response = _client().post(
        "/api/sessions/generate-title",
        json={"user_message": "Explain the redesigned web app\nwith details", "ai_response": "Sure"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "title": "Explain the redesigned web app"}
