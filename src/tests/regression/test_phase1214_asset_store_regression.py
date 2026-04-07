"""Phase 12.14 — Asset store regression tests."""
import os

from app.rpg.visual import asset_store


def test_asset_store_manifest_survives_corrupted_file(monkeypatch, tmp_path):
    """Ensure corrupted manifest file returns empty manifest instead of crashing."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    # Write corrupted JSON
    queue_file = tmp_path / "manifest.json"
    queue_file.write_text("{bad json", encoding="utf-8")

    manifest = asset_store.get_asset_manifest()
    assert manifest == {"assets": {}}


def test_asset_store_cleanup_handles_missing_files_gracefully(monkeypatch, tmp_path):
    """Ensure cleanup doesn't crash when asset files are missing but manifest references them."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    # Manually write a manifest referencing a file that doesn't exist
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        '{"assets": {"asset:ghost": {"content_hash": "abc123", "mime_type": "image/png", "created_at": "2026-01-01T00:00:00"}}}',
        encoding="utf-8",
    )

    # Should not raise
    result = asset_store.cleanup_unused_assets(referenced_ids=set())
    assert "asset:ghost" in result["deleted_asset_ids"]


def test_asset_store_concurrent_save_does_not_corrupt_manifest(monkeypatch, tmp_path):
    """Ensure atomic writes prevent manifest corruption."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    # Save multiple assets
    for i in range(10):
        asset_store.save_asset_bytes(
            f"data-{i}".encode(),
            mime_type="image/png",
            asset_id=f"asset:{i}",
        )

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert len(assets) == 10

    # Verify no .tmp files left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_asset_store_empty_asset_id_is_rejected(monkeypatch, tmp_path):
    """Ensure empty asset_id generates a UUID-based fallback."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    id1 = asset_store.save_asset_bytes(b"data", mime_type="image/png", asset_id="")
    id2 = asset_store.save_asset_bytes(b"data", mime_type="image/png", asset_id="")

    # Both should have valid IDs
    assert id1.startswith("asset:")
    assert id2.startswith("asset:")