"""Phase 12 — Visual Identity regression tests.

Ensures that Phase 12 changes don't break existing visual state behavior:
- ensure_visual_state remains idempotent
- character_ui_state still contains visual_identity
- scene illustration bounds are maintained
- image request bounds are maintained
"""
import json

from flask import Flask

from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp
from app.rpg.presentation.visual_state import (
    append_image_request,
    append_scene_illustration,
    ensure_visual_state,
    upsert_character_visual_identity,
)


def test_ensure_visual_state_idempotent_regression():
    """ensure_visual_state should be idempotent after Phase 12 additions."""
    one = ensure_visual_state({})
    two = ensure_visual_state(dict(one))
    assert one["presentation_state"]["visual_state"] == two["presentation_state"]["visual_state"]


def test_visual_state_bounds_regression():
    """Visual state bounds for scene_illustrations should still work."""
    simulation_state = {}
    for i in range(30):
        simulation_state = append_scene_illustration(
            simulation_state,
            {
                "scene_id": f"scene:{i}",
                "event_id": f"event:{i}",
                "title": f"Scene {i}",
            },
        )
    illustrations = simulation_state["presentation_state"]["visual_state"]["scene_illustrations"]
    assert len(illustrations) == 24


def test_image_request_bounds_regression():
    """Image request bounds should still work."""
    simulation_state = {}
    for i in range(30):
        simulation_state = append_image_request(
            simulation_state,
            {
                "request_id": f"req:{i}",
                "kind": "character_portrait",
                "target_id": f"npc:{i}",
            },
        )
    requests = simulation_state["presentation_state"]["visual_state"]["image_requests"]
    assert len(requests) == 24


def test_character_ui_state_contains_visual_identity_regression():
    """character_ui_state should contain visual_identity for each character."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {
                    "entity_id": "npc:test",
                    "speaker_name": "Test Character",
                    "role": "ally",
                }
            ]
        }
    }
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id="npc:test",
        identity={
            "portrait_url": "/test.png",
            "seed": 42,
            "status": "complete",
        },
    )

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/character_ui",
            data=json.dumps({
                "setup_payload": {
                    "simulation_state": simulation_state,
                }
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        characters = payload["character_ui_state"]["characters"]
        assert len(characters) == 1
        assert "visual_identity" in characters[0]


def test_scene_presentation_still_returns_visual_state_regression():
    """Scene presentation should still return visual_state."""
    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/presentation/scene",
            data=json.dumps({
                "setup_payload": {},
                "scene_state": {},
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert "visual_state" in payload
        assert "character_visual_identities" in payload["visual_state"]
        assert "scene_illustrations" in payload["visual_state"]
        assert "image_requests" in payload["visual_state"]