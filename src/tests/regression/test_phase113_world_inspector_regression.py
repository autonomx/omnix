"""Phase 11.3 — World Inspector regression tests.

Ensures world inspector features do not break existing functionality:
- Existing presentation routes still work
- Character inspector still works
- World inspector state is consistently returned
"""

import json

from flask import Flask

from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp


def _create_test_client():
    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)
    return app.test_client()


def test_scene_presentation_still_returns_character_state():
    """Ensure scene presentation still returns character_ui_state and character_inspector_state."""
    with _create_test_client() as client:
        response = client.post(
            "/api/rpg/presentation/scene",
            data=json.dumps({"setup_payload": {}, "scene_state": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_ui_state" in payload
        assert "character_inspector_state" in payload
        assert "world_inspector_state" in payload


def test_dialogue_presentation_still_returns_character_state():
    """Ensure dialogue presentation still returns character state."""
    with _create_test_client() as client:
        response = client.post(
            "/api/rpg/presentation/dialogue",
            data=json.dumps({"setup_payload": {}, "dialogue_state": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_ui_state" in payload
        assert "character_inspector_state" in payload
        assert "world_inspector_state" in payload


def test_world_inspector_state_shape_is_stable():
    """Ensure world_inspector_state has expected shape."""
    with _create_test_client() as client:
        response = client.post(
            "/api/rpg/world_inspector",
            data=json.dumps({"setup_payload": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        world_state = payload["world_inspector_state"]
        assert "summary" in world_state
        assert "threads" in world_state
        assert "thread_count" in world_state
        assert "factions" in world_state
        assert "locations" in world_state
        assert "factions" in world_state["factions"]
        assert "count" in world_state["factions"]
        assert "locations" in world_state["locations"]
        assert "count" in world_state["locations"]


def test_world_inspector_with_world_data():
    """Ensure world inspector correctly reflects world state when provided."""
    with _create_test_client() as client:
        simulation_state = {
            "faction_state": {
                "factions": {
                    "faction:guard": {"name": "City Guard"},
                }
            },
            "world_state": {
                "locations": {
                    "loc:market": {"name": "Market Square"},
                },
                "threads": [
                    {"id": "thread:1", "title": "Rising Tensions"},
                ],
            },
        }
        response = client.post(
            "/api/rpg/world_inspector",
            data=json.dumps({
                "setup_payload": {
                    "simulation_state": simulation_state,
                }
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        world_state = payload["world_inspector_state"]
        assert world_state["factions"]["count"] == 1
        assert world_state["locations"]["count"] == 1
        assert world_state["thread_count"] == 1


def test_narrative_recap_still_returns_character_state():
    """Ensure narrative recap still returns character state."""
    with _create_test_client() as client:
        response = client.post(
            "/narrative-recap",
            data=json.dumps({"setup_payload": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_ui_state" in payload
        assert "character_inspector_state" in payload
        assert "world_inspector_state" in payload


def test_character_inspector_still_works():
    """Ensure character inspector endpoint still works independently."""
    with _create_test_client() as client:
        response = client.post(
            "/api/rpg/character_inspector",
            data=json.dumps({"setup_payload": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_inspector_state" in payload


def test_character_ui_still_works():
    """Ensure character UI endpoint still works independently."""
    with _create_test_client() as client:
        response = client.post(
            "/api/rpg/character_ui",
            data=json.dumps({"setup_payload": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_ui_state" in payload