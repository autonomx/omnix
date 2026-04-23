from __future__ import annotations


def test_run_one_completion_persists_scene_without_pending_request_lookup(flask_client, monkeypatch):
    from app.rpg.api import rpg_presentation_routes

    session = {
        "manifest": {"id": "preview_test_scene"},
        "runtime_state": {},
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
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
            "request_status": "complete",
            "session_id": "preview_test_scene",
            "request_id": "scene:req1",
            "asset_id": "scene_illustration:scene:1:123",
            "image_url": "/generated-images/test_scene.png",
            "local_path": "resources/data/generated_images/test_scene.png",
            "kind": "scene_illustration",
            "target_id": "scene",
            "prompt": "The Rusty Flagon Tavern",
            "style": "rpg-scene",
            "model": "default",
            "seed": 123,
            "version": 1,
        },
    )

    response = flask_client.post("/api/rpg/visual/queue/run_one", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    visual_state = session["simulation_state"]["presentation_state"]["visual_state"]
    assert len(visual_state["scene_illustrations"]) == 1
    assert len(visual_state["visual_assets"]) == 1
    assert visual_state["scene_illustrations"][0]["image_url"] == "/generated-images/test_scene.png"
    assert visual_state["visual_assets"][0]["url"] == "/generated-images/test_scene.png"
