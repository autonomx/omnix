from __future__ import annotations

from app.rpg.session.runtime import (
    build_frontend_bootstrap_payload,
    ensure_visual_state,
)


def test_build_frontend_bootstrap_payload_includes_visual_state():
    simulation_state = ensure_visual_state({
        "presentation_state": {
            "visual_state": {
                "scene_illustrations": [
                    {
                        "scene_id": "loc_tavern",
                        "status": "complete",
                        "image_url": "/generated-images/test.png",
                    }
                ],
                "character_portraits": {}
            }
        }
    })

    session = {
        "manifest": {"id": "preview_123", "title": "Test"},
        "runtime_state": {},
        "simulation_state": simulation_state,
        "turn_result": {},
    }

    payload = build_frontend_bootstrap_payload(session)

    assert payload["session_id"] == "preview_123"
    assert "visual_state" in payload
    assert any(
        s.get("scene_id") == "loc_tavern" and s.get("image_url") == "/generated-images/test.png"
        for s in payload["visual_state"]["scene_illustrations"]
    )
