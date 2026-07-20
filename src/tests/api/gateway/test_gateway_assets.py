"""Contract tests for the shared asset gateway."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_asset_store_previews_image_manifest_import(tmp_path: Path, monkeypatch) -> None:
    from app.assets import SharedAssetStore
    import app.shared as shared

    existing = tmp_path / "image.png"
    existing.write_bytes(b"png")
    empty_legacy = tmp_path / "empty_legacy"
    empty_legacy.mkdir()
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(empty_legacy))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(empty_legacy / "voice_clones.json"))
    monkeypatch.setenv("OMNIX_LEGACY_AUDIO_DIRS", str(empty_legacy))
    monkeypatch.setenv("OMNIX_LEGACY_DOCUMENT_DIRS", str(empty_legacy))
    store = SharedAssetStore(tmp_path / "assets.json")

    preview = store.import_image_manifest_dry_run(
        {
            "assets": {
                "hero": {
                    "path": str(existing),
                    "mime_type": "image/png",
                    "hash": "abc",
                    "metadata": {"kind": "cover"},
                },
                "missing": {
                    "path": str(tmp_path / "missing.png"),
                    "mime_type": "image/png",
                    "hash": "def",
                    "metadata": {},
                },
            }
        }
    )

    assert preview.would_import == 2
    assert {asset.id for asset in preview.assets} == {"image:hero", "image:missing"}
    assert preview.missing_files == [
        {"asset_id": "missing", "path": str(tmp_path / "missing.png"), "reason": "file_missing"}
    ]
    assert store.list_assets().assets == []


def test_asset_store_import_preserves_missing_legacy_asset_diagnostics(tmp_path: Path, monkeypatch) -> None:
    from app.assets import SharedAssetStore
    import app.shared as shared

    existing = tmp_path / "scene.png"
    existing.write_bytes(b"png")
    missing = tmp_path / "missing.png"
    empty_legacy = tmp_path / "empty_legacy"
    empty_legacy.mkdir()
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(empty_legacy))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(empty_legacy / "voice_clones.json"))
    monkeypatch.setenv("OMNIX_LEGACY_AUDIO_DIRS", str(empty_legacy))
    monkeypatch.setenv("OMNIX_LEGACY_DOCUMENT_DIRS", str(empty_legacy))
    store = SharedAssetStore(tmp_path / "assets.json")

    imported = store.import_image_manifest(
        {
            "assets": {
                "scene": {
                    "path": str(existing),
                    "mime_type": "image/png",
                    "hash": "hash:scene",
                    "metadata": {"kind": "scene"},
                },
                "missing": {
                    "path": str(missing),
                    "mime_type": "image/png",
                    "hash": "hash:missing",
                    "metadata": {"kind": "legacy-reference"},
                },
            }
        }
    )

    listed = store.list_assets().assets

    assert imported.would_import == 2
    assert imported.missing_files == [
        {"asset_id": "missing", "path": str(missing), "reason": "file_missing"}
    ]
    assert {asset.id for asset in listed} == {"image:scene", "image:missing"}
    missing_asset = next(asset for asset in listed if asset.id == "image:missing")
    assert missing_asset.storage_path == str(missing)
    assert missing_asset.compat == {
        "legacy_system": "src/app/image/asset_store.py",
        "legacy_asset_id": "missing",
        "legacy_hash": "hash:missing",
    }


def test_gateway_assets_endpoint_uses_shared_store() -> None:
    from app.assets import AssetLegacyImportDryRun, AssetListResponse, AssetMigrationPreview
    from app.gateway.main import create_gateway_app

    class FakeAssetStore:
        def list_assets(self) -> AssetListResponse:
            return AssetListResponse(assets=[])

        def import_image_manifest_dry_run(self) -> AssetMigrationPreview:
            return AssetMigrationPreview(source="fake", would_import=0)

        def import_image_manifest(self) -> AssetMigrationPreview:
            return AssetMigrationPreview(source="fake", would_import=0)

        def preview_legacy_non_image_import(self) -> AssetLegacyImportDryRun:
            return AssetLegacyImportDryRun(source="fake legacy", would_import=0)

    client = TestClient(
        create_gateway_app(asset_store_factory=lambda: FakeAssetStore()),
        raise_server_exceptions=False,
    )

    response = client.get("/api/assets")
    assert response.status_code == 200
    assert response.json() == {"assets": []}

    dry_run = client.post("/api/assets/migrations/image/dry-run")
    assert dry_run.status_code == 200
    assert dry_run.json()["source"] == "fake"

    legacy_dry_run = client.post("/api/assets/migrations/legacy-non-image/dry-run")
    assert legacy_dry_run.status_code == 200
    assert legacy_dry_run.json()["source"] == "fake legacy"


def test_gateway_deletes_voice_clone_asset_and_local_source(tmp_path: Path, monkeypatch) -> None:
    import json

    from app.assets import AssetListResponse, AssetRecord, AssetType
    from app.gateway.main import create_gateway_app
    import app.shared as shared

    clone_dir = tmp_path / "voice_clones"
    clone_dir.mkdir()
    clone_path = clone_dir / "jinx2.wav"
    clone_path.write_bytes(b"voice")
    manifest_path = clone_dir / "voice_clones.json"
    manifest_path.write_text(json.dumps({"jinx2": {"voice_clone_id": "jinx2"}}), encoding="utf-8")
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(clone_dir))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(manifest_path))

    asset = AssetRecord(
        id="voice-cloning:jinx2",
        module="voice-cloning",
        type=AssetType.VOICE_PROFILE,
        mime_type="audio/wav",
        storage_path=str(clone_path),
        metadata={"profile_name": "jinx2", "voice_id": "jinx2"},
        created_at="2026-07-20T00:00:00Z",
    )

    class FakeAssetStore:
        def list_assets(self) -> AssetListResponse:
            return AssetListResponse(assets=[asset])

        def delete_asset(self, asset_id: str) -> dict[str, object]:
            assert asset_id == asset.id
            return {"deleted": True, "file_deleted": False}

    client = TestClient(create_gateway_app(asset_store_factory=lambda: FakeAssetStore()))

    response = client.delete("/api/voice-cloning/assets/voice-cloning:jinx2")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "asset_id": asset.id, "deleted": True, "file_deleted": True}
    assert not clone_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {}
