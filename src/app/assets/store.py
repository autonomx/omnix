"""Manifest-backed shared asset store with compatibility read-through."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import resources_data_root

from .models import AssetListResponse, AssetMigrationPreview, AssetRecord, AssetType


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_asset_manifest_path() -> Path:
    override = os.environ.get("OMNIX_ASSETS_MANIFEST_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "assets" / "manifest.json"


class SharedAssetStore:
    """Small JSON manifest store for shared asset metadata."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self.manifest_path = Path(manifest_path) if manifest_path else default_asset_manifest_path()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def list_assets(self) -> AssetListResponse:
        return AssetListResponse(assets=list(self._load_manifest().values()))

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        manifest = self._load_manifest()
        manifest[asset.id] = asset
        self._save_manifest(manifest)
        return asset

    def preview_image_manifest_import(
        self,
        image_manifest: dict[str, Any] | None = None,
    ) -> AssetMigrationPreview:
        if image_manifest is None:
            from app.image.asset_store import get_image_asset_manifest

            image_manifest = get_image_asset_manifest()

        records: list[AssetRecord] = []
        missing: list[dict[str, Any]] = []
        for asset_id, payload in dict((image_manifest or {}).get("assets") or {}).items():
            path = str((payload or {}).get("path") or "")
            record = AssetRecord(
                id=f"image:{asset_id}",
                module="image",
                type=AssetType.IMAGE,
                mime_type=str((payload or {}).get("mime_type") or "image/png"),
                storage_path=path,
                metadata=dict((payload or {}).get("metadata") or {}),
                created_at=_utcnow(),
                compat={
                    "legacy_system": "src/app/image/asset_store.py",
                    "legacy_asset_id": asset_id,
                    "legacy_hash": (payload or {}).get("hash") or "",
                },
            )
            records.append(record)
            if path and not Path(path).is_file():
                missing.append({"asset_id": asset_id, "path": path, "reason": "file_missing"})

        return AssetMigrationPreview(
            source="src/app/image/asset_store.py",
            would_import=len(records),
            missing_files=missing,
            assets=records,
        )

    def import_image_manifest_dry_run(self, image_manifest: dict[str, Any] | None = None) -> AssetMigrationPreview:
        return self.preview_image_manifest_import(image_manifest=image_manifest)

    def import_image_manifest(self, image_manifest: dict[str, Any] | None = None) -> AssetMigrationPreview:
        preview = self.preview_image_manifest_import(image_manifest=image_manifest)
        manifest = self._load_manifest()
        for asset in preview.assets:
            manifest[asset.id] = asset
        self._save_manifest(manifest)
        return preview

    def _load_manifest(self) -> dict[str, AssetRecord]:
        if not self.manifest_path.is_file():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {
            asset_id: AssetRecord(**payload)
            for asset_id, payload in dict(raw.get("assets") or {}).items()
        }

    def _save_manifest(self, assets: dict[str, AssetRecord]) -> None:
        payload = {
            "assets": {
                asset_id: asset.model_dump(mode="json")
                for asset_id, asset in sorted(assets.items())
            }
        }
        self.manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_asset_store() -> SharedAssetStore:
    return SharedAssetStore()
