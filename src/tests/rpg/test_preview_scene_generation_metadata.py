from __future__ import annotations


def test_run_one_uses_request_metadata_not_fallbacks(monkeypatch):
    from app.rpg.visual import queue_runner

    monkeypatch.setattr(queue_runner, "_claim_next_live_visual_job", lambda lease_seconds=300: {
        "job_id": "job:test",
        "lease_token": "lease:test",
        "_resolved_session_id": "preview_test",
        "_resolved_request_id": "scene:req1",
        "_resolved_request": {
            "request_id": "scene:req1",
            "kind": "scene_illustration",
            "target_id": "scene:1:22222",
            "prompt": "Scene illustration of The Rusty Flagon Tavern",
            "style": "rpg-scene",
            "model": "default",
            "seed": 184965,
            "version": None,
            "status": "pending",
        },
    })
    monkeypatch.setattr(queue_runner, "image_generation_enabled", lambda: True)
    monkeypatch.setattr(queue_runner, "_generate_preview_image_for_request", lambda **kwargs: {
        "ok": True,
        "image_bytes": b"fakepng",
        "mime_type": "image/png",
        "asset_id": "",
    })
    monkeypatch.setattr(queue_runner, "save_asset_bytes", lambda *args, **kwargs: "resources/data/generated_images/test_hash.png")
    monkeypatch.setattr(queue_runner, "complete_image_job", lambda **kwargs: {})

    result = queue_runner.run_one_queued_job()

    assert result["ok"] is True
    assert result["processed"] is True
    assert result["target_id"] == "scene:1:22222"
    assert result["prompt"] == "Scene illustration of The Rusty Flagon Tavern"
    assert result["style"] == "rpg-scene"
    assert result["seed"] == 184965


def test_update_image_request_drops_completed_requests():
    from app.rpg.presentation.visual_state import (
        append_image_request,
        ensure_visual_state,
        update_image_request,
    )

    simulation_state = ensure_visual_state({})
    simulation_state = append_image_request(simulation_state, {
        "request_id": "scene:req1",
        "kind": "scene_illustration",
        "target_id": "scene:1:22222",
        "status": "pending",
    })
    simulation_state = update_image_request(simulation_state, request_id="scene:req1", patch={"status": "complete"})
    requests = simulation_state["presentation_state"]["visual_state"]["image_requests"]
    assert requests == []