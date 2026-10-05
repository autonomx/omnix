from __future__ import annotations

import json
from pathlib import Path

from app.assets import SharedAssetStore
from app.assets.store import LEGACY_IMAGE_MANIFEST
from app.platform.image import asset_store as legacy_asset_store
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings, reset_port_bindings_for_tests


def test_shared_assets_read_through_legacy_image_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.persistence.runtime.uses_postgresql_runtime", lambda: False)
    image_dir = tmp_path / "legacy-images"
    image_dir.mkdir()
    image_path = image_dir / "legacy.png"
    image_path.write_bytes(b"png")
    legacy_manifest = image_dir / "manifest.json"
    legacy_manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "legacy-one": {
                        "path": str(image_path),
                        "mime_type": "image/png",
                        "hash": "abc123",
                        "metadata": {"title": "Legacy one"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(legacy_asset_store, "ASSET_DIR", str(image_dir))
    monkeypatch.setattr(legacy_asset_store, "MANIFEST_PATH", str(legacy_manifest))

    # Composition binds the image feature's legacy manifest reader (ADR-0016).
    install_port_bindings(PortBindings.build([
        PortBinding(LEGACY_IMAGE_MANIFEST, legacy_asset_store.get_image_asset_manifest, owner="image"),
    ]))
    shared_manifest = tmp_path / "shared" / "manifest.json"
    store = SharedAssetStore(manifest_path=shared_manifest)
    assets = {asset.id: asset for asset in store.list_assets().assets}

    assert assets["image:legacy-one"].storage_path == str(image_path)
    assert assets["image:legacy-one"].compat["legacy_asset_id"] == "legacy-one"
    assert not shared_manifest.exists()

    migration = store.import_image_manifest()
    assert migration.would_import == 1
    assert shared_manifest.is_file()
    assert {asset.id for asset in store.list_assets().assets} >= {"image:legacy-one"}
    reset_port_bindings_for_tests()


def test_without_the_image_feature_there_is_no_legacy_image_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.persistence.runtime.uses_postgresql_runtime", lambda: False)
    reset_port_bindings_for_tests()
    store = SharedAssetStore(manifest_path=tmp_path / "shared" / "manifest.json")
    assert store.preview_image_manifest_import().assets == []
