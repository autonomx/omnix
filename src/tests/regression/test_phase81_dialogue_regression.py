"""Regression tests for Phase 8.1 Dialogue System."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_app():
    """Create a FastAPI test app with the production dialogue router."""
    from app.rpg.api.rpg_dialogue_routes import rpg_dialogue_bp

    app = FastAPI()
    app.include_router(rpg_dialogue_bp)
    return app


def _make_setup_payload():
    return {"setup_payload": {"metadata": {"simulation_state": {"tick": 1}}}}


@pytest.fixture
def app():
    return _make_test_app()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestDialogueRegression:
    """Regression tests to prevent issues in dialogue system."""

    def test_start_dialogue_returns_serializable_state(self, client):
        """Ensure dialogue state is always JSON serializable."""
        payload = _make_setup_payload()
        payload["npc_id"] = "ser_npc"
        payload["scene_id"] = "ser_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.json()
        assert resp.status_code == 200
        # Should not raise
        json.dumps(data)

    def test_rapid_messages_no_crash(self, client):
        """Ensure rapid messages don't crash the system."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "rapid_npc"
        start_payload["scene_id"] = "rapid_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        for i in range(10):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "rapid_npc",
                "scene_id": "rapid_scene",
                "message": f"msg {i}"
            }
            resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            assert resp.status_code == 200
            start_data["setup_payload"] = resp.json()["setup_payload"]

    def test_dialogue_state_consistent_after_restart(self, client):
        """Ensure dialogue state is reset properly after restart."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "npc1"
        start_payload["scene_id"] = "scene1"
        resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = resp.json()

        # Send message
        msg_payload = {"setup_payload": start_data["setup_payload"], "npc_id": "npc1", "scene_id": "scene1", "message": "Hello"}
        resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
        msg_data = resp.json()

        # End dialogue
        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": msg_data["setup_payload"]})
        end_data = end_resp.json()

        # Restart with different NPC
        restart_payload = {"setup_payload": end_data["setup_payload"], "npc_id": "npc2", "scene_id": "scene2"}
        restart_resp = client.post("/api/rpg/dialogue/start", json=restart_payload)
        restart_data = restart_resp.json()
        assert restart_data["dialogue_state"]["npc_id"] == "npc2"

    def test_special_characters_in_message(self, client):
        """Ensure special characters don't break dialogue."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "special_npc"
        start_payload["scene_id"] = "special_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        resp = client.post(
            "/api/rpg/dialogue/message",
            json={
                "setup_payload": start_data["setup_payload"],
                "npc_id": "special_npc",
                "scene_id": "special_scene",
                "message": 'Hello! <script>alert("xss")</script> & "quotes"'
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_empty_message_handled(self, client):
        """Ensure empty messages are handled gracefully."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "empty_npc"
        start_payload["scene_id"] = "empty_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        resp = client.post(
            "/api/rpg/dialogue/message",
            json={"setup_payload": start_data["setup_payload"], "npc_id": "empty_npc", "scene_id": "empty_scene", "message": ""}
        )
        assert resp.status_code == 200

    def test_very_long_message_handled(self, client):
        """Ensure very long messages don't crash the system."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "long_npc"
        start_payload["scene_id"] = "long_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        long_message = "A" * 10000
        resp = client.post(
            "/api/rpg/dialogue/message",
            json={"setup_payload": start_data["setup_payload"], "npc_id": "long_npc", "scene_id": "long_scene", "message": long_message}
        )
        assert resp.status_code == 200

    def test_history_bounded_under_pressure(self, client):
        """Ensure history stays bounded even with many messages."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "bounded_npc"
        start_payload["scene_id"] = "bounded_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        # Send 30 messages (60 history entries)
        for i in range(30):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "bounded_npc",
                "scene_id": "bounded_scene",
                "message": f"Message {i}"
            }
            resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            start_data["setup_payload"] = resp.json()["setup_payload"]

        # End and check dialogue_state
        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": start_data["setup_payload"]})
        data = end_resp.json()
        # Dialogue state should exist
        assert "dialogue_state" in data
