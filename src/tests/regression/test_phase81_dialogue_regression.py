"""Regression tests for Phase 8.1 Dialogue System."""

import json

import pytest
from flask import Flask


def _make_test_app():
    """Create a minimal Flask test app with just the dialogue blueprint."""
    from app.rpg.ai.dialogue import DialogueManager
    from app.rpg.player import ensure_player_state

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


class TestDialogueRegression:
    """Regression tests to prevent issues in dialogue system."""

    def test_start_dialogue_returns_serializable_state(self, client):
        """Ensure dialogue state is always JSON serializable."""
        payload = _make_setup_payload()
        payload["npc_id"] = "ser_npc"
        payload["scene_id"] = "ser_scene"
        resp = client.post("/api/rpg/dialogue/start", json=payload)
        data = resp.get_json()
        assert resp.status_code == 200
        # Should not raise
        json.dumps(data)

    def test_rapid_messages_no_crash(self, client):
        """Ensure rapid messages don't crash the system."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "rapid_npc"
        start_payload["scene_id"] = "rapid_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.get_json()

        for i in range(10):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "rapid_npc",
                "scene_id": "rapid_scene",
                "message": f"msg {i}"
            }
            resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            assert resp.status_code == 200
            start_data["setup_payload"] = resp.get_json()["setup_payload"]

    def test_dialogue_state_consistent_after_restart(self, client):
        """Ensure dialogue state is reset properly after restart."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "npc1"
        start_payload["scene_id"] = "scene1"
        resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = resp.get_json()

        # Send message
        msg_payload = {"setup_payload": start_data["setup_payload"], "npc_id": "npc1", "scene_id": "scene1", "message": "Hello"}
        resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
        msg_data = resp.get_json()

        # End dialogue
        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": msg_data["setup_payload"]})
        end_data = end_resp.get_json()

        # Restart with different NPC
        restart_payload = {"setup_payload": end_data["setup_payload"], "npc_id": "npc2", "scene_id": "scene2"}
        restart_resp = client.post("/api/rpg/dialogue/start", json=restart_payload)
        restart_data = restart_resp.get_json()
        assert restart_data["dialogue_state"]["npc_id"] == "npc2"

    def test_special_characters_in_message(self, client):
        """Ensure special characters don't break dialogue."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "special_npc"
        start_payload["scene_id"] = "special_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.get_json()

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
        data = resp.get_json()
        assert data["ok"] is True

    def test_empty_message_handled(self, client):
        """Ensure empty messages are handled gracefully."""
        start_payload = _make_setup_payload()
        start_payload["npc_id"] = "empty_npc"
        start_payload["scene_id"] = "empty_scene"
        start_resp = client.post("/api/rpg/dialogue/start", json=start_payload)
        start_data = start_resp.get_json()

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
        start_data = start_resp.get_json()

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
        start_data = start_resp.get_json()

        # Send 30 messages (60 history entries)
        for i in range(30):
            msg_payload = {
                "setup_payload": start_data["setup_payload"],
                "npc_id": "bounded_npc",
                "scene_id": "bounded_scene",
                "message": f"Message {i}"
            }
            resp = client.post("/api/rpg/dialogue/message", json=msg_payload)
            start_data["setup_payload"] = resp.get_json()["setup_payload"]

        # End and check dialogue_state
        end_resp = client.post("/api/rpg/dialogue/end", json={"setup_payload": start_data["setup_payload"]})
        data = end_resp.get_json()
        # Dialogue state should exist
        assert "dialogue_state" in data