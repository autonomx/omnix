from __future__ import annotations


def test_run_one_completion_persists_visual_state(client, monkeypatch):
    from app.rpg.api import rpg_presentation_routes

    session = {
        "manifest": {"id": "preview_test_visual"},
        "runtime_state": {},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {
                            "request_id": "scene:req1",
                            "kind": "scene_illustration",
                            "target_id": "loc_tavern",
                            "version": 1,
                            "seed": 123,
                            "style": "rpg-scene",
                            "model": "default",
                            "prompt": "The Rusty Flagon Tavern",
                            "status": "pending",
                        }
                    ],
                    "scene_illustrations": [],
                    "visual_assets": [],
                    "character_visual_identities": {},
                }
            }
        },
    }

    monkeypatch.setattr(rpg_presentation_routes, "load_runtime_session", lambda session_id: session)
    monkeypatch.setattr(rpg_presentation_routes, "save_runtime_session", lambda updated: None)
    monkeypatch.setattr(
        rpg_presentation_routes,
        "run_one_queued_job",
        lambda lease_seconds=300: {
            "ok": True,
            "processed": True,
            "session_id": "preview_test_visual",
            "request_id": "scene:req1",
            "request_status": "complete",
            "asset_id": "scene_illustration:loc_tavern:1:123",
            "image_url": "/generated-images/test.png",
            "local_path": "resources/data/generated_images/test.png",
        },
    )

    response = client.post("/api/rpg/visual/queue/run_one", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    visual_state = session["simulation_state"]["presentation_state"]["visual_state"]
    assert visual_state["scene_illustrations"]
    assert visual_state["visual_assets"]
    assert visual_state["scene_illustrations"][0]["image_url"] == "/generated-images/test.png"
    assert visual_state["visual_assets"][0]["url"] == "/generated-images/test.png"

    # Verify the request was marked complete
    assert len(visual_state["image_requests"]) == 1
    assert visual_state["image_requests"][0]["status"] == "complete"
    assert visual_state["image_requests"][0]["asset_id"] == "scene_illustration:loc_tavern:1:123"
    assert visual_state["image_requests"][0]["image_url"] == "/generated-images/test.png"
