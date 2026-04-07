"""Phase 12.14 — Asset store functional tests."""
import os

from app.rpg.visual import asset_store


def test_asset_store_end_to_end_workflow(monkeypatch, tmp_path):
    """Test full asset lifecycle: save, retrieve, cleanup."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    # Save assets
    id1 = asset_store.save_asset_bytes(b"image-data-1", mime_type="image/png", asset_id="asset:char1")
    id2 = asset_store.save_asset_bytes(b"image-data-2", mime_type="image/jpeg", asset_id="asset:scene1")

    assert id1 == "asset:char1"
    assert id2 == "asset:scene1"

    # Retrieve paths
    path1 = asset_store.get_asset_path("asset:char1")
    path2 = asset_store.get_asset_path("asset:scene1")
    assert path1 is not None
    assert path2 is not None
    assert os.path.exists(path1)
    assert os.path.exists(path2)

    # Verify manifest
    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert len(assets) == 2


def test_asset_store_cleanup_removes_unreferenced(monkeypatch, tmp_path):
    """Test that cleanup removes assets not in the referenced set."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    asset_store.save_asset_bytes(b"keep-data", mime_type="image/png", asset_id="asset:keep")
    asset_store.save_asset_bytes(b"drop-data", mime_type="image/png", asset_id="asset:drop")

    result = asset_store.cleanup_unused_assets(referenced_ids={"asset:keep"})
    assert "asset:drop" in result["deleted_asset_ids"]

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert "asset:keep" in assets
    assert "asset:drop" not in assets


def test_asset_store_dedup_saves_same_content_once(monkeypatch, tmp_path):
    """Test that identical content is stored only once."""
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)

    id1 = asset_store.save_asset_bytes(b"same", mime_type="image/png", asset_id="asset:a")
    id2 = asset_store.save_asset_bytes(b"same", mime_type="image/png", asset_id="asset:b")

    # Content dedup returns existing asset_id
    assert id1 == id2

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert len(assets) == 1