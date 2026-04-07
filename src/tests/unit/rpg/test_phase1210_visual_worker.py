"""Phase 12.10 / 12.11 — Visual worker unit tests."""
from app.rpg.presentation.visual_state import (
    append_image_request,
    get_pending_image_requests,
    update_image_request,
)
from app.rpg.visual.providers.base import ImageGenerationResult
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


def test_update_image_request_preserves_blocked_status():
    """Blocked requests must stay blocked after normalization."""
    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "req:blocked",
            "kind": "character_portrait",
            "target_id": "npc:blocked",
            "prompt": "Blocked test",
            "status": "pending",
        },
    )

    simulation_state = update_image_request(
        simulation_state,
        request_id="req:blocked",
        patch={"status": "blocked", "error": "moderation_blocked"},
    )

    requests = simulation_state["presentation_state"]["visual_state"]["image_requests"]
    found = next(req for req in requests if req.get("request_id") == "req:blocked")
    assert found["status"] == "blocked"
    assert found["error"] == "moderation_blocked"


def test_worker_uses_revised_prompt_for_asset_record(monkeypatch):
    """Successful provider results should persist revised_prompt into the asset record."""
    class _StubProvider:
        provider_name = "stub"

        def generate(self, **kwargs):
            return ImageGenerationResult(
                ok=True,
                status="complete",
                image_bytes=b"fakepng",
                mime_type="image/png",
                revised_prompt="Rewritten portrait prompt",
                moderation_status="approved",
                moderation_reason="",
            )

    monkeypatch.setattr("app.rpg.visual.worker.get_image_provider", lambda: _StubProvider())
    monkeypatch.setattr("app.rpg.visual.worker.save_asset_bytes", lambda asset_id, image_bytes, mime_type: f"/tmp/{asset_id}.png")

    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:revise:1",
            "kind": "character_portrait",
            "target_id": "npc:revise",
            "prompt": "Original prompt",
            "seed": 42,
            "style": "rpg-portrait",
            "model": "gpt-image-1",
            "status": "pending",
        },
    )

    out = process_pending_image_requests(simulation_state, limit=1)
    visual_assets = out["presentation_state"]["visual_state"]["visual_assets"]
    assert len(visual_assets) == 1
    assert visual_assets[0]["prompt"] == "Rewritten portrait prompt"


def test_worker_marks_moderation_blocked_requests_as_blocked(monkeypatch):
    """Moderation-blocked provider results must persist request status as blocked."""
    class _StubProvider:
        provider_name = "stub"

        def generate(self, **kwargs):
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_http_400",
                image_bytes=b"",
                mime_type="image/png",
                revised_prompt="",
                moderation_status="blocked",
                moderation_reason="Rejected by safety policy",
            )

    monkeypatch.setattr("app.rpg.visual.worker.get_image_provider", lambda: _StubProvider())

    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:blocked-by-provider:1",
            "kind": "character_portrait",
            "target_id": "npc:blocked-by-provider",
            "prompt": "Original prompt",
            "seed": 42,
            "style": "rpg-portrait",
            "model": "gpt-image-1",
            "status": "pending",
        },
    )

    out = process_pending_image_requests(simulation_state, limit=1)
    requests = out["presentation_state"]["visual_state"]["image_requests"]
    found = next(req for req in requests if req.get("request_id") == "portrait:npc:blocked-by-provider:1")
    assert found["status"] == "blocked"
    assert found["error"] == "openai_http_400"


def test_worker_stays_pending_on_retryable_failure(monkeypatch):
    """Retryable provider errors should keep request pending if attempts remain."""
    call_count = 0

    class _FlakyProvider:
        provider_name = "flaky"

        def generate(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_network_error",
                image_bytes=b"",
                mime_type="image/png",
                revised_prompt="",
                moderation_status="approved",
                moderation_reason="",
            )

    monkeypatch.setattr("app.rpg.visual.worker.get_image_provider", lambda: _FlakyProvider())

    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:flaky:1",
            "kind": "character_portrait",
            "target_id": "npc:flaky",
            "prompt": "Original prompt",
            "seed": 42,
            "style": "rpg-portrait",
            "model": "gpt-image-1",
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
        },
    )

    out = process_pending_image_requests(simulation_state, limit=1)
    requests = out["presentation_state"]["visual_state"]["image_requests"]
    found = next(req for req in requests if req.get("request_id") == "portrait:npc:flaky:1")
    # After first failure with max_attempts=3, should stay pending
    assert found["status"] == "pending"
    assert found["attempts"] == 1


def test_worker_fails_after_max_attempts(monkeypatch):
    """Exhausted retries should mark request as failed."""
    class _AlwaysFailProvider:
        provider_name = "alwaysfail"

        def generate(self, **kwargs):
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_network_error",
                image_bytes=b"",
                mime_type="image/png",
                revised_prompt="",
                moderation_status="approved",
                moderation_reason="",
            )

    monkeypatch.setattr("app.rpg.visual.worker.get_image_provider", lambda: _AlwaysFailProvider())

    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:exhausted:1",
            "kind": "character_portrait",
            "target_id": "npc:exhausted",
            "prompt": "Original prompt",
            "seed": 42,
            "style": "rpg-portrait",
            "model": "gpt-image-1",
            "status": "pending",
            "attempts": 2,
            "max_attempts": 3,
        },
    )

    out = process_pending_image_requests(simulation_state, limit=1)
    requests = out["presentation_state"]["visual_state"]["image_requests"]
    found = next(req for req in requests if req.get("request_id") == "portrait:npc:exhausted:1")
    # Attempt 3 == max_attempts → should be terminal failed
    assert found["status"] == "failed"
    assert found["attempts"] == 3


def test_worker_skips_exhausted_requests(monkeypatch):
    """Requests already at max_attempts should be marked failed and skipped."""
    call_count = 0

    class _CountingProvider:
        provider_name = "counting"

        def generate(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return ImageGenerationResult(
                ok=True,
                status="complete",
                image_bytes=b"fakepng",
                mime_type="image/png",
                revised_prompt="",
                moderation_status="approved",
                moderation_reason="",
            )

    monkeypatch.setattr("app.rpg.visual.worker.get_image_provider", lambda: _CountingProvider())

    simulation_state = {"presentation_state": {"visual_state": {}}}
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": "portrait:npc:skip:1",
            "kind": "character_portrait",
            "target_id": "npc:skip",
            "prompt": "Should not run",
            "seed": 42,
            "style": "rpg-portrait",
            "model": "gpt-image-1",
            "status": "pending",
            "attempts": 3,
            "max_attempts": 3,
        },
    )

    out = process_pending_image_requests(simulation_state, limit=1)
    requests = out["presentation_state"]["visual_state"]["image_requests"]
    found = next(req for req in requests if req.get("request_id") == "portrait:npc:skip:1")
    # Already exhausted → should never call provider
    assert call_count == 0
    assert found["status"] == "failed"
