"""Compatibility wrapper for global asset store."""
from __future__ import annotations

from typing import Any, Dict, Optional, Set

from app.image.asset_store import (
    cleanup_unused_image_assets,
    get_image_asset_manifest,
    register_image_asset_file,
    save_image_asset_bytes,
)


def save_asset_bytes(
    data: bytes,
    *,
    mime_type: str = "image/png",
    asset_id: Optional[str] = None,
    kind: str = "",
    target_id: str = "",
) -> str:
    resolved_asset_id = asset_id or ""
    metadata: Dict[str, Any] = {
        "kind": kind,
        "target_id": target_id,
    }
    return save_image_asset_bytes(
        data or b"",
        mime_type=mime_type,
        asset_id=resolved_asset_id,
        metadata=metadata,
    )


def get_asset_manifest() -> Dict[str, Any]:
    return get_image_asset_manifest()


def cleanup_unused_assets(referenced_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    # Global cleanup API currently ignores referenced_ids and performs safe cleanup.
    return cleanup_unused_image_assets()


__all__ = [
    "save_asset_bytes",
    "register_image_asset_file",
    "get_asset_manifest",
    "cleanup_unused_assets",
    "save_image_asset_bytes",
    "get_image_asset_manifest",
    "cleanup_unused_image_assets",
]
