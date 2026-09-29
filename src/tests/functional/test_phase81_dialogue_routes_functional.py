"""Functional tests for Phase 8.1 Dialogue Routes."""

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


class TestDialogueRoutesFunctional:
    """Functional tests for dialogue API routes."""

    def test_start_dialogue_success(self, client):
        """Test starting a dialogue session via API."""
        payload = _make_setup_payload()
        payload["npc_id"] = "test_npc"
        payload["scene_id"] = "test_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["dialogue_state"]["active"] is True

    def test_start_dialogue_no_npc(self, client):
        """Test starting dialogue without npc_id."""
        payload = _make_setup_payload()
        payload["scene_id"] = "test_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.json()
        assert resp.status_code == 200
        # Should still work but npc_id will be empty

    def test_send_message_success(self, client):
        """Test sending a dialogue message."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "test_npc"
        start_payload["scene_id"] = "test_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        msg_payload = {"setup_payload": start_data["setup_payload"], "npc_id": "test_npc", "scene_id": "test_scene", "message": "Hello!"}
        resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
        data = resp.json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert "reply" in data
        assert "dialogue_state" in data

    def test_end_dialogue_success(self, client):
        """Test ending a dialogue session."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "test_npc"
        start_payload["scene_id"] = "test_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        end_payload = {"setup_payload": start_data["setup_payload"]}
        resp = client.post("/api/rpg/dialogue/end", json=end_payload)
        data = resp.json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["dialogue_state"]["active"] is False

    def test_dialogue_flow_complete(self, client):
        """Test complete dialogue flow: start -> message -> end."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "flow_npc"
        start_payload["scene_id"] = "flow_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.json()

        for i in range(3):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "flow_npc",
                "scene_id": "flow_scene",
                "message": f"Message {i}",
            }
            msg_resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            assert msg_resp.status_code == 200
            start_data["setup_payload"] = msg_resp.json()["setup_payload"]

        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": start_data["setup_payload"]})
        assert end_resp.status_code == 200
        data = end_resp.json()
        assert data["dialogue_state"]["active"] is False

    def test_multiple_dialogues_isolated(self, client):
        """Test that multiple adventure dialogues are isolated."""
        payload1 = _make_setup_payload()
        payload1["npc_id"] = "npc1"
        payload1["scene_id"] = "scene1"
        resp1 = client.post("/api/rpg/dialogue/start", json=payload1)

        payload2 = _make_setup_payload()
        payload2["npc_id"] = "npc2"
        payload2["scene_id"] = "scene2"
        resp2 = client.post("/api/rpg/dialogue/start", json=payload2)

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        data1 = resp1.json()
        data2 = resp2.json()
        assert data1["dialogue_state"]["npc_id"] == "npc1"
        assert data2["dialogue_state"]["npc_id"] == "npc2"
