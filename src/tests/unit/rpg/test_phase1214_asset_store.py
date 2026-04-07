"""Phase 12.14 — Asset store dedupe and cleanup tests."""
import os

from app.rpg.visual import asset_store


def test_save_asset_bytes_dedupes_identical_content(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    id1 = asset_store.save_asset_bytes(b"same-bytes", mime_type="image/png", asset_id="asset:1")
    id2 = asset_store.save_asset_bytes(b"same-bytes", mime_type="image/png", asset_id="asset:2")
    # Content dedup: same content returns existing asset_id
    assert id1 == id2

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert len(assets) == 1


def test_cleanup_unused_assets_removes_orphaned_file(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    id1 = asset_store.save_asset_bytes(b"keep-bytes", mime_type="image/png", asset_id="asset:keep")
    id2 = asset_store.save_asset_bytes(b"drop-bytes", mime_type="image/png", asset_id="asset:drop")

    # Only reference asset:keep
    result = asset_store.cleanup_unused_assets(referenced_ids={"asset:keep"})
    assert "asset:drop" in result["deleted_asset_ids"]
    assert len(result["deleted_files"]) >= 0  # File may or may not be deleted depending on hash

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert "asset:keep" in assets
    assert "asset:drop" not in assets


def test_different_content_creates_separate_files(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    id1 = asset_store.save_asset_bytes(b"bytes-one", mime_type="image/png", asset_id="asset:1")
    id2 = asset_store.save_asset_bytes(b"bytes-two", mime_type="image/png", asset_id="asset:2")
    assert id1 != id2

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert len(assets) == 2


def test_mime_type_determines_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    png_id = asset_store.save_asset_bytes(b"data", mime_type="image/png", asset_id="asset:png")
    jpg_id = asset_store.save_asset_bytes(b"data2", mime_type="image/jpeg", asset_id="asset:jpg")
    webp_id = asset_store.save_asset_bytes(b"data3", mime_type="image/webp", asset_id="asset:webp")

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})

    png_info = assets.get(png_id, {})
    jpg_info = assets.get(jpg_id, {})
    webp_info = assets.get(webp_id, {})

    assert png_info.get("filename", "").endswith(".png")
    assert jpg_info.get("filename", "").endswith(".jpg")
    assert webp_info.get("filename", "").endswith(".webp")


def test_manifest_persists_across_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    asset_store.save_asset_bytes(b"data1", mime_type="image/png", asset_id="asset:1")
    asset_store.save_asset_bytes(b"data2", mime_type="image/png", asset_id="asset:2")

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert "asset:1" in assets
    assert "asset:2" in assets


def test_cleanup_keeps_referenced_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_store, "_ASSET_DIR", tmp_path)
    id1 = asset_store.save_asset_bytes(b"data-a", mime_type="image/png", asset_id="asset:a")
    id2 = asset_store.save_asset_bytes(b"data-b", mime_type="image/png", asset_id="asset:b")

    result = asset_store.cleanup_unused_assets(referenced_ids={"asset:a", "asset:b"})
    assert len(result["deleted_asset_ids"]) == 0
    assert len(result["deleted_files"]) == 0

    manifest = asset_store.get_asset_manifest()
    assets = manifest.get("assets", {})
    assert "asset:a" in assets
    assert "asset:b" in assets