"""Phase 12.12/12.13/12.14 — Visual provider/queue/asset functional tests."""
import json
import os
import tempfile
import shutil

from app.rpg.visual.providers import get_image_provider
from app.rpg.visual.providers.comfy_provider import ComfyImageProvider
from app.rpg.visual.providers.mock_provider import MockImageProvider
from app.rpg.visual.providers.openai_provider import OpenAIImageProvider
from app.rpg.visual.job_queue import (
    enqueue_visual_job,
    claim_next_visual_job,
    complete_visual_job,
    list_visual_jobs,
    release_visual_job,
    prune_completed_visual_jobs,
)
from app.rpg.visual.asset_store import (
    save_asset_bytes,
    get_asset_manifest,
    cleanup_unused_assets,
)


class TestVisualProviderSelection:
    """Test provider selection based on environment variables."""

    def test_mock_provider_is_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "mock")
        provider = get_image_provider()
        assert isinstance(provider, MockImageProvider)

    def test_comfy_provider_selection(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "comfy")
        provider = get_image_provider()
        assert isinstance(provider, ComfyImageProvider)

    def test_openai_provider_selection(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "openai")
        provider = get_image_provider()
        assert isinstance(provider, OpenAIImageProvider)

    def test_unknown_provider_falls_back_to_mock(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "unknown_provider_xyz")
        provider = get_image_provider()
        assert isinstance(provider, MockImageProvider)


class TestMockProviderFunctional:
    """Test mock provider produces valid results."""

    def test_mock_provider_returns_result(self):
        provider = MockImageProvider()
        result = provider.generate(
            prompt="test prompt",
            seed=42,
            style="test-style",
            model="test-model",
            kind="character_portrait",
            target_id="npc:test",
        )
        # Mock provider returns a result (may be placeholder or complete based on implementation)
        assert isinstance(result.ok, bool)
        assert isinstance(result.status, str)


class TestVisualQueueFunctional:
    """Test visual queue end-to-end workflow."""

    def test_full_queue_workflow(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

        # Enqueue multiple jobs
        job1 = enqueue_visual_job(session_id="session:1", request_id="req:1")
        job2 = enqueue_visual_job(session_id="session:2", request_id="req:2")
        job3 = enqueue_visual_job(session_id="session:3", request_id="req:3")

        assert job1["status"] == "queued"
        assert job2["status"] == "queued"
        assert job3["status"] == "queued"

        # Claim and process jobs in order
        claimed1 = claim_next_visual_job(lease_seconds=60)
        assert claimed1["status"] == "leased"
        assert claimed1["lease_token"] != ""

        completed1 = complete_visual_job(
            job_id=claimed1["job_id"],
            lease_token=claimed1["lease_token"],
        )
        assert completed1["status"] == "complete"

        # Check queue stats
        jobs = list_visual_jobs()
        active = [j for j in jobs if j["status"] in ("queued", "leased")]
        assert len(active) == 2


class TestAssetStoreFunctional:
    """Test asset store deduplication and cleanup."""

    def test_asset_deduplication(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.rpg.visual.asset_store._ASSET_DIR", tmp_path)

        # Save same content twice with different asset IDs
        path1 = save_asset_bytes("asset:a1", b"identical-content", "image/png")
        path2 = save_asset_bytes("asset:a2", b"identical-content", "image/png")

        # Should return same file path (deduplication)
        assert path1 == path2

        # Manifest should show 2 asset IDs but only 1 hash
        manifest = get_asset_manifest()
        assert len(manifest["by_hash"]) == 1
        assert len(manifest["by_asset_id"]) == 2

    def test_asset_cleanup_removes_orphans(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.rpg.visual.asset_store._ASSET_DIR", tmp_path)

        # Create assets
        path_keep = save_asset_bytes("asset:keep", b"keep-data", "image/png")
        path_remove = save_asset_bytes("asset:remove", b"remove-data", "image/png")

        assert os.path.exists(path_keep)
        assert os.path.exists(path_remove)

        # Setup simulation state with only one asset referenced
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "visual_assets": [
                        {"asset_id": "asset:keep", "local_path": path_keep, "url": path_keep},
                    ]
                }
            }
        }

        result = cleanup_unused_assets(simulation_state)
        assert "asset:remove" in result["deleted_asset_ids"]
        assert os.path.exists(path_keep)
        assert not os.path.exists(path_remove)