from __future__ import annotations

from pathlib import Path
from typing import Any

from app.assets.models import AssetListResponse, AssetMigrationPreview, AssetRecord

from .blob_store import LocalBlobStore
from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


class PostgresSharedAssetStoreAdapter:
    def __init__(
        self,
        manifest_path: str | Path | None = None,
        *,
        database: PostgresDatabase | None = None,
        blob_store: LocalBlobStore | None = None,
    ) -> None:
        if manifest_path is not None:
            raise RuntimeError(
                "manifest-backed asset authority is retired; use the Phase 8 importer"
            )
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)
        self.blob_store = blob_store or LocalBlobStore()

    def list_assets(self) -> AssetListResponse:
        with unit_of_work(self.database) as work:
            records = work.assets.list_assets(self.context, limit=500)
            work.rollback()
        return AssetListResponse(assets=[self._asset(record) for record in records])

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        with unit_of_work(self.database) as work:
            existing = work.assets.get_asset(self.context, asset.id)
            work.rollback()
        if existing is not None:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE omnix_assets
                       SET module = %s, asset_type = %s, mime_type = %s,
                           metadata = %s::jsonb, compat = %s::jsonb,
                           revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND id = %s
                    """,
                    (
                        asset.module,
                        self._enum_value(asset.type),
                        asset.mime_type,
                        self._json(asset.metadata),
                        self._json(asset.compat),
                        self.context.workspace_id,
                        asset.id,
                    ),
                )
            with unit_of_work(self.database) as work:
                record = work.assets.get_asset(self.context, asset.id)
                work.rollback()
            if record is None:
                raise RuntimeError(f"asset update disappeared: {asset.id}")
            return self._asset(record)

        source = Path(str(asset.storage_path or ""))
        if not source.is_file():
            raise FileNotFoundError(str(source))
        content = source.read_bytes()
        storage_key = f"assets/{self._safe(asset.id)}/{source.name}"
        blob = self.blob_store.put_bytes(storage_key, content)
        try:
            with unit_of_work(self.database) as work:
                record = work.assets.create(
                    self.context,
                    {
                        "id": asset.id,
                        "module": asset.module,
                        "asset_type": self._enum_value(asset.type),
                        "mime_type": asset.mime_type,
                        "byte_size": blob["byte_size"],
                        "checksum_sha256": blob["checksum_sha256"],
                        "storage_provider": blob["storage_provider"],
                        "storage_key": blob["storage_key"],
                        "metadata": dict(asset.metadata),
                        "compat": {
                            **dict(asset.compat),
                            "legacy_source_path": str(source),
                        },
                    },
                )
                work.commit()
        except Exception:
            if blob.get("created"):
                self.blob_store.delete(storage_key)
            raise
        return self._asset(record)

    def delete_asset(self, asset_id: str, *, delete_file: bool = True) -> dict[str, Any]:
        with unit_of_work(self.database) as work:
            record = work.assets.get_asset(self.context, asset_id)
            if record is None:
                work.rollback()
                return {
                    "ok": False,
                    "asset_id": asset_id,
                    "deleted": False,
                    "file_deleted": False,
                }
            deleted = work.assets.mark_deleted(
                self.context,
                asset_id=asset_id,
                expected_revision=record["revision"],
            )
            work.commit()
        file_deleted = self.blob_store.delete(record["storage_key"]) if delete_file else False
        return {
            "ok": True,
            "asset_id": asset_id,
            "deleted": deleted["lifecycle_status"] == "deleted",
            "file_deleted": file_deleted,
        }

    def preview_image_manifest_import(
        self,
        image_manifest: dict[str, Any] | None = None,
    ) -> AssetMigrationPreview:
        del image_manifest
        return AssetMigrationPreview(
            source="retired-manifest-authority",
            would_import=0,
            missing_files=[],
            assets=[],
        )

    def import_image_manifest_dry_run(
        self,
        image_manifest: dict[str, Any] | None = None,
    ) -> AssetMigrationPreview:
        return self.preview_image_manifest_import(image_manifest)

    def import_image_manifest(
        self,
        image_manifest: dict[str, Any] | None = None,
    ) -> AssetMigrationPreview:
        raise RuntimeError(
            "runtime manifest import is retired; use scripts/import_legacy_persistence_bundle.py"
        )

    def _asset(self, record: dict[str, Any]) -> AssetRecord:
        path = self.blob_store.root.joinpath(*record["storage_key"].split("/"))
        return AssetRecord(
            id=record["id"],
            module=record["module"],
            type=record["asset_type"],
            mime_type=record["mime_type"],
            storage_path=str(path),
            metadata=dict(record.get("metadata") or {}),
            created_at=record["created_at"],
            compat=dict(record.get("compat") or {}),
        )

    @staticmethod
    def _enum_value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _safe(value: str) -> str:
        import re

        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "asset"

    @staticmethod
    def _json(value: Any) -> str:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
