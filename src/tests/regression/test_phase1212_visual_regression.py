"""Phase 12.12/12.13/12.14 — Visual system regression tests.

Ensures that new provider, queue, and asset store functionality
doesn't break existing visual worker flows and state management.
"""
import json
import os

from app.rpg.visual.providers import get_image_provider
from app.rpg.visual.providers.base import BaseImageProvider, ImageGenerationResult
from app.rpg.visual.providers.mock_provider import MockImageProvider
from app.rpg.visual.worker import process_pending_image_requests


class TestProviderRegistryRegression:
    """Ensure provider registry maintains backward compatibility."""

    def test_default_provider_is_mock(self, monkeypatch):
        monkeypatch.delenv("RPG_IMAGE_PROVIDER", raising=False)
        provider = get_image_provider()
        assert isinstance(provider, MockImageProvider)

    def test_provider_has_generate_method(self, monkeypatch):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "mock")
        provider = get_image_provider()
        assert hasattr(provider, "generate")
        assert callable(getattr(provider, "generate"))

    def test_generate_returns_result_type(self, monkeypatch):
        monkeypatch.setenv("RPG_IMAGE_PROVIDER", "mock")
        provider = get_image_provider()
        result = provider.generate(
            prompt="test",
            seed=1,
            style="test",
            model="test",
            kind="character_portrait",
            target_id="test",
        )
        assert isinstance(result, ImageGenerationResult)


class TestAssetStoreCompatibilityRegression:
    """Ensure asset store maintains compatibility with existing flows."""

    def test_asset_store_has_required_functions(self):
        from app.rpg.visual import asset_store

        assert hasattr(asset_store, "save_asset_bytes")
        assert hasattr(asset_store, "build_asset_filename")
        assert hasattr(asset_store, "cleanup_unused_assets")

    def test_cleanup_unused_assets_returns_expected_structure(self, monkeypatch, tmp_path):
        from app.rpg.visual import asset_store
        monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

        result = asset_store.cleanup_unused_assets({})
        assert "simulation_state" in result
        assert "deleted_asset_ids" in result
        assert "deleted_files" in result
        assert isinstance(result["deleted_asset_ids"], list)
        assert isinstance(result["deleted_files"], list)
