"""
Search functionality tests – migrated from test_search.py.

Tests session search workflow using the Flask test client.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _mock_llm_post():
    """Return a context-manager mock for ``requests.post`` used by the chat route."""
    mock = patch("app.requests.post")
    return mock


class TestSearchSessionEndpoints:
    """Session endpoints used by the search feature."""

    def test_get_sessions_returns_list(self, flask_client):
        response = flask_client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert isinstance(data["sessions"], list)

    def test_get_sessions_includes_metadata(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Hello", "session_id": sid},
                content_type="application/json",
            )

        response = flask_client.get("/api/sessions")
        assert len(response.json["sessions"]) > 0
        assert "id" in response.json["sessions"][0]
        flask_client.delete(f"/api/sessions/{sid}")

    def test_get_session_by_id_includes_messages(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "Searchable content here"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Test message", "session_id": sid},
                content_type="application/json",
            )

        response = flask_client.get(f"/api/sessions/{sid}")
        session = response.json["session"]
        assert "messages" in session
        assert len(session["messages"]) > 0
        assert "role" in session["messages"][0]
        assert "content" in session["messages"][0]
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_scenario_user_message_found(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        unique_term = "xyzsearchterm123"

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "AI response"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": f"User said {unique_term}", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        user_msgs = [m for m in session["messages"] if m["role"] == "user"]
        assert any(unique_term in m["content"] for m in user_msgs)
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_scenario_ai_message_found(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        unique_term = "aisearchterm456"

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": f"AI says {unique_term}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Hello", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        ai_msgs = [m for m in session["messages"] if m["role"] == "assistant"]
        assert any(unique_term in m["content"] for m in ai_msgs)
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_case_insensitive(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "UPPERCASE SEARCH"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "lowercase search", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        all_content = " ".join(m["content"].lower() for m in session["messages"])
        assert "uppercase search" in all_content
        assert "lowercase search" in all_content
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_multiple_sessions(self, flask_client):
        sids = []
        for i in range(3):
            create_resp = flask_client.post("/api/sessions")
            sid = create_resp.json["session_id"]
            sids.append(sid)

            with _mock_llm_post() as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {
                    "choices": [{"message": {"content": f"Response from session {i}"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
                }
                flask_client.post(
                    "/api/chat",
                    json={"message": f"Message in session {i}", "session_id": sid},
                    content_type="application/json",
                )

        response = flask_client.get("/api/sessions")
        assert len(response.json["sessions"]) >= 3

        for sid in sids:
            session = flask_client.get(f"/api/sessions/{sid}").json["session"]
            assert "messages" in session

        for sid in sids:
            flask_client.delete(f"/api/sessions/{sid}")

    def test_empty_session_search(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        assert len(session["messages"]) == 0
        flask_client.delete(f"/api/sessions/{sid}")


class TestSearchAPIIntegration:
    """Integration tests simulating the frontend search workflow."""

    def test_search_workflow_full(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        search_term = "uniquepythoncode789"

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": f"Here is some {search_term} in the response"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Tell me about python", "session_id": sid},
                content_type="application/json",
            )

        sessions = flask_client.get("/api/sessions").json["sessions"]
        found_results = []
        for s in sessions:
            s_resp = flask_client.get(f"/api/sessions/{s['id']}")
            if s_resp.status_code == 200 and s_resp.json.get("success"):
                full = s_resp.json["session"]
                for msg in full.get("messages", []):
                    if search_term in msg.get("content", "").lower():
                        found_results.append(msg)

        assert len(found_results) > 0
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_no_results(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "This is about cats"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Tell me about cats", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        search_term = "nonexistentdogquery123"
        found = any(search_term in m.get("content", "") for m in session.get("messages", []))
        assert not found
        flask_client.delete(f"/api/sessions/{sid}")

    def test_search_special_characters(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        special_term = "test@email.com"

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": f"Contact: {special_term}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "What is your email?", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        content_text = " ".join(m.get("content", "") for m in session.get("messages", []))
        assert special_term in content_text
        flask_client.delete(f"/api/sessions/{sid}")


class TestSearchEdgeCases:
    """Edge cases for search."""

    def test_very_long_message_search(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        long_content = "word " * 1000 + "uniquelongterm999" + " word" * 1000

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": long_content}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1000, "total_tokens": 1005},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Long response", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        found = any("uniquelongterm999" in m.get("content", "") for m in session.get("messages", []))
        assert found
        flask_client.delete(f"/api/sessions/{sid}")

    def test_unicode_content_search(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        unicode_term = "日本語テスト"

        with _mock_llm_post() as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": f"Content: {unicode_term}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            }
            flask_client.post(
                "/api/chat",
                json={"message": "Japanese", "session_id": sid},
                content_type="application/json",
            )

        session = flask_client.get(f"/api/sessions/{sid}").json["session"]
        content_text = " ".join(m.get("content", "") for m in session.get("messages", []))
        assert unicode_term in content_text
        flask_client.delete(f"/api/sessions/{sid}")

    def test_deleted_session_not_searchable(self, flask_client):
        create_resp = flask_client.post("/api/sessions")
        sid = create_resp.json["session_id"]
        flask_client.delete(f"/api/sessions/{sid}")
        response = flask_client.get(f"/api/sessions/{sid}")
        assert response.status_code == 404
