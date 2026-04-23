from __future__ import annotations

from app.rpg.session.runtime import build_frontend_bootstrap_payload, ensure_visual_state


def test_build_frontend_bootstrap_payload_includes_visual_state():
    simulation_state = ensure_visual_state({
        "player_state": {
            "stats": {},
            "skills": {},
            "inventory_state": {"items": [], "equipment": {}, "currency": {}},
        },
        "presentation_state": {
            "visual_state": {
                "scene_illustrations": [
                    {
                        "scene_id": "scene:loc_tavern",
                        "status": "complete",
                        "image_url": "/generated-images/test_scene.png",
                        "local_path": "resources/data/generated_images/test_scene.png",
                    }
                ],
                "character_portraits": {},
            }
        },
    })

    session = {
        "manifest": {"id": "preview_test_1", "title": "Test Adventure"},
        "runtime_state": {
            "opening": "Opening line",
            "npcs": [],
            "current_scene": {
                "scene_id": "scene:test",
                "items": [],
                "available_checks": [],
                "present_npc_ids": [],
            },
        },
        "simulation_state": simulation_state,
        "turn_result": {"narration": "Narration line"},
    }

    payload = build_frontend_bootstrap_payload(session)

    assert payload["session_id"] == "preview_test_1"
    assert payload["narration"] == "Narration line"
    assert "visual_state" in payload
    assert payload["visual_state"]["scene_illustrations"][0]["image_url"] == "/generated-images/test_scene.png"


def test_build_frontend_bootstrap_payload_uses_session_turn_result_not_runtime_last_turn_result():
    simulation_state = ensure_visual_state({
        "player_state": {
            "stats": {},
            "skills": {},
            "inventory_state": {"items": [], "equipment": {}, "currency": {}},
        },
    })

    session = {
        "manifest": {"id": "preview_test_2", "title": "Test Adventure"},
        "runtime_state": {
            "opening": "Opening line",
            "npcs": [],
            "current_scene": {
                "scene_id": "scene:test",
                "items": [],
                "available_checks": [],
                "present_npc_ids": [],
            },
            "last_turn_result": {"narration": "WRONG_SOURCE"},
        },
        "simulation_state": simulation_state,
        "turn_result": {"narration": "RIGHT_SOURCE"},
    }

    payload = build_frontend_bootstrap_payload(session)

    assert payload["narration"] == "RIGHT_SOURCE"
