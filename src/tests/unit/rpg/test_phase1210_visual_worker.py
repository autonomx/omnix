"""Phase 12.10 — Visual worker unit tests."""
from app.rpg.presentation.visual_state import (
    append_image_request,
    get_pending_image_requests,
    update_image_request,
)
from app.rpg.visual.worker import process_pending_image_requests


def test_process_pending_image_requests_mock_provider():
    """Test that pending image requests are processed via mock provider."""
    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:test:1",
            "kind": "character_portrait",
            "target_id": "npc:test",
            "prompt": "A stern guard captain",
            "seed": 123,
            "style": "rpg-portrait",
            "model": "default",
            "status": "pending",
        },
    )

    out = process_pending_image_requests(simulation_state, limit=4)
    visual_state = out["presentation_state"]["visual_state"]
    assert "image_requests" in visual_state
    assert len(visual_state["image_requests"]) >= 1


def test_get_pending_image_requests_returns_only_pending():
    """Test that only pending requests are returned."""
    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "req:1",
            "kind": "character_portrait",
            "target_id": "npc:a",
            "prompt": "Test prompt",
            "status": "pending",
        },
    )
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "req:2",
            "kind": "scene_illustration",
            "target_id": "scene:b",
            "prompt": "Another prompt",
            "status": "complete",
        },
    )

    pending = get_pending_image_requests(simulation_state)
    assert len(pending) == 1
    assert pending[0]["request_id"] == "req:1"


def test_update_image_request_applies_patch():
    """Test that update_image_request correctly patches fields."""
    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "req:patch_test",
            "kind": "character_portrait",
            "target_id": "npc:patch",
            "prompt": "Patch test",
            "status": "pending",
        },
    )

    simulation_state = update_image_request(
        simulation_state,
        request_id="req:patch_test",
        patch={"status": "complete", "error": ""},
    )

    requests = simulation_state["presentation_state"]["visual_state"]["image_requests"]
    found = None
    for req in requests:
        if req.get("request_id") == "req:patch_test":
            found = req
            break

    assert found is not None
    assert found["status"] == "complete"
    assert found["error"] == ""