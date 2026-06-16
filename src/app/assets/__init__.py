"""Shared asset/artifact library."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .legacy_documents import (
    _DOCUMENT_MIME_TYPES,
    _legacy_document_roots,
    legacy_document_assets,
)
from .models import (
    AssetLegacyImportDryRun,
    AssetLegacyRootScan,
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
    AssetType,
)
from .store import (
    _AUDIO_MIME_TYPES,
    _legacy_audio_roots,
    SharedAssetStore as ManifestSharedAssetStore,
)


def _root_scan(family: str, path: Path) -> AssetLegacyRootScan:
    return AssetLegacyRootScan(family=family, path=str(path), exists=path.is_dir() or path.is_file())


def _skipped_files(family: str, roots: list[Path], supported_suffixes: set[str]) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in supported_suffixes:
                continue
            skipped.append(
                {
                    "family": family,
                    "path": str(path),
                    "extension": suffix.lstrip("."),
                    "reason": "unsupported_file_type",
                }
            )
    return skipped


class SharedAssetStore(ManifestSharedAssetStore):
    """Shared asset store with compatibility read-through for legacy documents."""

    def list_assets(self) -> AssetListResponse:
        assets = {asset.id: asset for asset in super().list_assets().assets}
        for asset in legacy_document_assets():
            assets.setdefault(asset.id, asset)
        return AssetListResponse(assets=list(assets.values()))

    def preview_legacy_non_image_import(self) -> AssetLegacyImportDryRun:
        """Summarize non-image legacy assets without mutating any source."""
        manifest_assets = super()._load_manifest()
        legacy_assets = [
            *super()._legacy_voice_clone_assets(),
            *super()._legacy_audio_assets(),
            *legacy_document_assets(),
        ]

        category_counts: dict[str, int] = {}
        for asset in legacy_assets:
            category_counts[asset.type.value] = category_counts.get(asset.type.value, 0) + 1

        collision_asset_ids = sorted({asset.id for asset in legacy_assets if asset.id in manifest_assets})
        import_candidates = [asset for asset in legacy_assets if asset.id not in manifest_assets]

        audio_roots = _legacy_audio_roots()
        document_roots = _legacy_document_roots()
        roots_scanned = [
            *_voice_clone_roots(),
            *[_root_scan("audio", root) for root in audio_roots],
            *[_root_scan("documents", root) for root in document_roots],
        ]
        skipped_files = [
            *_skipped_files("audio", audio_roots, set(_AUDIO_MIME_TYPES)),
            *_skipped_files("documents", document_roots, set(_DOCUMENT_MIME_TYPES)),
        ]
        warnings = []
        if collision_asset_ids:
            warnings.append(
                f"{len(collision_asset_ids)} legacy asset id(s) already exist in the shared manifest; manifest records remain authoritative."
            )

        return AssetLegacyImportDryRun(
            source="legacy non-image read-through assets",
            would_import=len(import_candidates),
            category_counts=dict(sorted(category_counts.items())),
            roots_scanned=roots_scanned,
            collision_asset_ids=collision_asset_ids,
            skipped_files=skipped_files,
            warnings=warnings,
            assets=import_candidates,
        )


def _voice_clone_roots() -> list[AssetLegacyRootScan]:
    try:
        import app.shared as shared
    except Exception:
        return []

    roots: list[AssetLegacyRootScan] = []
    clones_dir = getattr(shared, "VOICE_CLONES_DIR", None)
    clones_file = getattr(shared, "VOICE_CLONES_FILE", None)
    if clones_dir:
        roots.append(_root_scan("voice_cloning", Path(str(clones_dir))))
    if clones_file:
        roots.append(_root_scan("voice_cloning_manifest", Path(str(clones_file))))
    return roots


def default_asset_store() -> SharedAssetStore:
    return SharedAssetStore()


__all__ = [
    "AssetListResponse",
    "AssetLegacyImportDryRun",
    "AssetLegacyRootScan",
    "AssetMigrationPreview",
    "AssetRecord",
    "AssetType",
    "SharedAssetStore",
    "default_asset_store",
]
