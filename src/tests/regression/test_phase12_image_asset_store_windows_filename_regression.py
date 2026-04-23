from __future__ import annotations

import os


def test_save_image_asset_bytes_sanitizes_windows_invalid_filename_chars(tmp_path, monkeypatch):
    """
    Regression:
    asset_id values used by RPG image generation often contain colons, e.g.
    'scene_illustration:scene:1:22222'.

    Those are valid logical ids, but they must not be used raw as filenames on
    Windows.
    """
    from app.image import asset_store

    monkeypatch.setattr(asset_store, "ASSET_DIR", str(tmp_path / "generated_images"))
    monkeypatch.setattr(asset_store, "MANIFEST_PATH", str(tmp_path / "generated_images" / "manifest.json"))

    path = asset_store.save_image_asset_bytes(
        b"fakepngbytes",
        mime_type="image/png",
        asset_id="scene_illustration:scene:1:22222",
        metadata={"kind": "scene_illustration", "target_id": "scene"},
    )

    assert os.path.isfile(path)
    assert path.endswith(".png")
    assert ":" not in os.path.basename(path)

    manifest = asset_store.get_image_asset_manifest()
    assert "scene_illustration:scene:1:22222" in manifest["assets"]
    assert manifest["assets"]["scene_illustration:scene:1:22222"]["path"] == path


def test_safe_asset_filename_component_preserves_stable_nonempty_name():
    from app.image.asset_store import _safe_asset_filename_component

    assert _safe_asset_filename_component("scene_illustration:scene:1:22222") == "scene_illustration_scene_1_22222"
    assert _safe_asset_filename_component("") == "asset"
    assert _safe_asset_filename_component("   ") == "asset"
