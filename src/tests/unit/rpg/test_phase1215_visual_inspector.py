"""Phase 12.15 — Visual inspector unit tests."""
from app.rpg.presentation.visual_inspector import build_visual_inspector_payload


def test_build_visual_inspector_payload_surfaces_requests_assets_queue_and_manifest():
    simulation_state = {
        "presentation_state": {
            "visual_state": {
                "image_requests": [
                    {
                        "request_id": "req:1",
                        "kind": "character_portrait",
                        "target_id": "npc:a",
                        "status": "pending",
                        "attempts": 1,
                        "max_attempts": 3,
                    }
                ],
                "visual_assets": [
                    {
                        "asset_id": "asset:1",
                        "kind": "character_portrait",
                        "target_id": "npc:a",
                        "status": "complete",
                        "url": "/tmp/a.png",
                    }
                ],
            }
        }
    }
    queue_jobs = [{"job_id": "job:1", "session_id": "s1", "request_id": "req:1", "status": "queued"}]
    asset_manifest = {
        "assets": {
            "asset:1": {
                "hash": "abc",
                "filename": "abc.png",
                "mime_type": "image/png",
                "size": 42,
            }
        }
    }

    payload = build_visual_inspector_payload(
        simulation_state,
        queue_jobs=queue_jobs,
        asset_manifest=asset_manifest,
    )

    assert payload["request_count"] == 1
    assert payload["asset_count"] == 1
    assert payload["queue_job_count"] == 1
    assert payload["manifest_asset_count"] == 1


def test_build_visual_inspector_payload_handles_empty_state():
    payload = build_visual_inspector_payload({})
    assert payload["request_count"] == 0
    assert payload["asset_count"] == 0
    assert payload["queue_job_count"] == 0
    assert payload["manifest_asset_count"] == 0
    assert payload["requests"] == []
    assert payload["assets"] == []
    assert payload["queue_jobs"] == []
    assert payload["asset_manifest"] == []
    assert "queue_normalize_route" in payload["actions"]


def test_build_visual_inspector_payload_strips_and_normalizes_fields():
    simulation_state = {
        "presentation_state": {
            "visual_state": {
                "image_requests": [
                    {
                        "request_id": "  req:2  ",
                        "kind": "scene_illustration",
                        "target_id": "scene:1",
                        "status": "complete",
                        "attempts": None,
                        "max_attempts": None,
                        "error": None,
                    }
                ]
            }
        }
    }
    payload = build_visual_inspector_payload(simulation_state)
    assert payload["requests"][0]["request_id"] == "req:2"
    assert payload["requests"][0]["attempts"] == 0
    assert payload["requests"][0]["error"] == ""