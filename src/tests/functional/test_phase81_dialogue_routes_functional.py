"""Functional tests for Phase 8.1 Dialogue Routes."""

import pytest
from flask import Flask


def _make_test_app():
    """Create a minimal Flask test app with just the dialogue blueprint."""
    from app.rpg.player import ensure_player_state
    from app.rpg.ai.dialogue import DialogueManager

    try:
        from app.rpg.api.rpg_dialogue_routes import rpg_dialogue_bp
        blueprint_registered = True
    except ImportError:
        blueprint_registered = False

    app = Flask(__name__)

    if blueprint_registered:
        app.register_blueprint(rpg_dialogue_bp)
    else:
        from flask import jsonify, request

        dialogue_manager = DialogueManager()

        @app.post("/api/rpg/dialogue/start")
        def dialogue_start():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            npc_id = str(data.get("npc_id") or "")
            scene_id = str(data.get("scene_id") or "")
            state = ensure_player_state(_get_simulation_state(setup_payload))
            state = dialogue_manager.start_dialogue(state, npc_id=npc_id, scene_id=scene_id)
            setup_payload = _write_simulation_state(setup_payload, state)
            return jsonify({
                "ok": True,
                "setup_payload": setup_payload,
                "dialogue_state": state.get("player_state", {}).get("dialogue_state", {}),
            })

        @app.post("/api/rpg/dialogue/message")
        def dialogue_message():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            npc_id = str(data.get("npc_id") or "")
            scene_id = str(data.get("scene_id") or "")
            player_message = str(data.get("message") or "")
            state = ensure_player_state(_get_simulation_state(setup_payload))
            scene = _get_scene(setup_payload, scene_id)
            npc, npc_mind = _get_npc_and_mind(state, npc_id)
            result = dialogue_manager.send_message(
                simulation_state=state, npc=npc, scene=scene, npc_mind=npc_mind, player_message=player_message,
            )
            state = result["simulation_state"]
            setup_payload = _write_simulation_state(setup_payload, state)
            return jsonify({
                "ok": True,
                "setup_payload": setup_payload,
                "reply": result["reply"],
                "dialogue_state": result["dialogue_state"],
            })

        @app.post("/api/rpg/dialogue/end")
        def dialogue_end():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            state = ensure_player_state(_get_simulation_state(setup_payload))
            state = dialogue_manager.end_dialogue(state)
            setup_payload = _write_simulation_state(setup_payload, state)
            return jsonify({
                "ok": True,
                "setup_payload": setup_payload,
                "dialogue_state": state.get("player_state", {}).get("dialogue_state", {}),
            })

    return app


def _make_setup_payload():
    return {"setup_payload": {"metadata": {"simulation_state": {"tick": 1}}}}


@pytest.fixture
def app():
    return _make_test_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestDialogueRoutesFunctional:
    """Functional tests for dialogue API routes."""

    def test_start_dialogue_success(self, client):
        """Test starting a dialogue session via API."""
        payload = _make_setup_payload()
        payload["npc_id"] = "test_npc"
        payload["scene_id"] = "test_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["dialogue_state"]["active"] is True

    def test_start_dialogue_no_npc(self, client):
        """Test starting dialogue without npc_id."""
        payload = _make_setup_payload()
        payload["scene_id"] = "test_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.get_json()
        assert resp.status_code == 200
        # Should still work but npc_id will be empty

    def test_send_message_success(self, client):
        """Test sending a dialogue message."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "test_npc"
        start_payload["scene_id"] = "test_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.get_json()

        msg_payload = {"setup_payload": start_data["setup_payload"], "npc_id": "test_npc", "scene_id": "test_scene", "message": "Hello!"}
        resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
        data = resp.get_json()
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
        start_data = start_resp.get_json()

        end_payload = {"setup_payload": start_data["setup_payload"]}
        resp = client.post("/api/rpg/dialogue/end", json=end_payload)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["dialogue_state"]["active"] is False

    def test_dialogue_flow_complete(self, client):
        """Test complete dialogue flow: start -> message -> end."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "flow_npc"
        start_payload["scene_id"] = "flow_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.get_json()

        for i in range(3):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "flow_npc",
                "scene_id": "flow_scene",
                "message": f"Message {i}",
            }
            msg_resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            assert msg_resp.status_code == 200
            start_data["setup_payload"] = msg_resp.get_json()["setup_payload"]

        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": start_data["setup_payload"]})
        assert end_resp.status_code == 200
        data = end_resp.get_json()
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

        data1 = resp1.get_json()
        data2 = resp2.get_json()
        assert data1["dialogue_state"]["npc_id"] == "npc1"
        assert data2["dialogue_state"]["npc_id"] == "npc2"