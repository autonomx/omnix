from __future__ import annotations

from app.rpg.presentation.visual_state import append_image_request, ensure_visual_state


def test_append_image_request_persists_into_simulation_state():
    simulation_state = ensure_visual_state({})
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "scene:req1",
            "kind": "scene_illustration",
            "target_id": "scene",
            "prompt": "The Rusty Flagon Tavern",
            "seed": 123,
            "style": "rpg-scene",
            "model": "default",
            "status": "pending",
        },
    )

    visual_state = simulation_state["presentation_state"]["visual_state"]
    assert len(visual_state["image_requests"]) == 1
    assert visual_state["image_requests"][0]["request_id"] == "scene:req1"


def test_append_scene_illustration_persists_into_simulation_state():
    from app.rpg.presentation.visual_state import append_scene_illustration

    simulation_state = ensure_visual_state({})
    simulation_state = append_scene_illustration(
        simulation_state,
        {
            "scene_id": "loc_tavern",
            "event_id": "scene:req1",
            "title": "The Rusty Flagon Tavern",
            "image_url": "/generated-images/test.png",
            "local_path": "resources/data/generated_images/test.png",
            "asset_id": "scene_illustration:loc_tavern:1:123",
            "status": "complete",
        },
    )

    visual_state = simulation_state["presentation_state"]["visual_state"]
    assert len(visual_state["scene_illustrations"]) == 1
    assert visual_state["scene_illustrations"][0]["image_url"] == "/generated-images/test.png"
