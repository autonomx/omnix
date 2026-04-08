"""Phase 12.10 / 12.14 — Asset file store with dedupe and cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_ASSET_DIR = Path("data/rpg_generated_assets")
_MANIFEST = "manifest.json"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _ensure_asset_dir() -> Path:
    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    return _ASSET_DIR


def _manifest_path() -> Path:
    _ensure_asset_dir()
    return _ASSET_DIR / _MANIFEST


def _read_manifest() -> Dict[str, Any]:
    path = _manifest_path()
    if not path.exists():
        return {"assets": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"assets": {}}
    return {"assets": _safe_dict(data.get("assets"))}


def _write_manifest(data: Dict[str, Any]) -> None:
    _ensure_asset_dir()
    path = _manifest_path()
    tmp = Path(f"{path}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _ext_for_mime(mime_type: str) -> str:
    mime_type = _safe_str(mime_type).strip().lower()
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    return ".png"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_asset_bytes(
    data: bytes,
    *,
    mime_type: str = "image/png",
    asset_id: Optional[str] = None,
    kind: str = "",
    target_id: str = "",
) -> str:
    """Save image bytes with content-hash deduplication.

    Returns the asset_id (UUID-based simulation identity).
    Content hash is used only for storage deduplication.
    """
    _ensure_asset_dir()
    data = data or b""
    mime_type = _safe_str(mime_type).strip() or "image/png"

    manifest = _read_manifest()
    assets = _safe_dict(manifest.get("assets"))

    content_hash = _sha256_hex(data)
    ext = _ext_for_mime(mime_type)

    # Dedupe by content hash — reuse existing asset_id if content matches
    for aid, info in assets.items():
        if _safe_str(info.get("hash")).strip() == content_hash:
            return aid

    # New asset — generate UUID-based identity
    if not asset_id:
        asset_id = f"asset:{uuid.uuid4().hex}"
    asset_id = _safe_str(asset_id).strip()

    # Store file using content hash (deduped), but identity is UUID
    filename = f"{content_hash}{ext}"
    path = str(_ASSET_DIR / filename)

    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)

    assets[asset_id] = {
        "asset_id": asset_id,
        "hash": content_hash,
        "filename": filename,
        "mime_type": mime_type,
        "size": len(data),
        "kind": _safe_str(kind).strip(),
        "target_id": _safe_str(target_id).strip(),
    }
    manifest["assets"] = assets
    _write_manifest(manifest)
    return asset_id


def get_asset_path(asset_id: str) -> Optional[str]:
    """Return the file path for a given asset_id (computed from filename)."""
    manifest = _read_manifest()
    assets = _safe_dict(manifest.get("assets"))
    info = _safe_dict(assets.get(asset_id))
    filename = _safe_str(info.get("filename")).strip()
    if not filename:
        return None
    _ensure_asset_dir()
    return str(_ASSET_DIR / filename)


def get_asset_manifest() -> Dict[str, Any]:
    """Return the full asset manifest."""
    return _read_manifest()


def cleanup_unused_assets(referenced_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Remove orphaned assets not in the referenced_ids set.

    If referenced_ids is None, no cleanup is performed (safe no-op).
    """
    if referenced_ids is None:
        return {"deleted_asset_ids": [], "deleted_files": []}

    manifest = _read_manifest()
    assets = _safe_dict(manifest.get("assets"))

    deleted_asset_ids: List[str] = []
    deleted_files: List[str] = []

    # Track which content hashes are still needed
    live_hashes: Set[str] = set()
    new_assets = {}

    for asset_id, info in assets.items():
        info = _safe_dict(info)
        if asset_id in referenced_ids:
            new_assets[asset_id] = info
            asset_hash = _safe_str(info.get("hash")).strip()
            if asset_hash:
                live_hashes.add(asset_hash)
        else:
            deleted_asset_ids.append(asset_id)

    # Remove orphaned files by scanning directory
    _ensure_asset_dir()
    for filename in os.listdir(_ASSET_DIR):
        if filename == _MANIFEST:
            continue

        filepath = os.path.join(_ASSET_DIR, filename)
        if not os.path.isfile(filepath):
            continue

        # filename format: <hash>.<ext>
        file_hash = filename.split(".", 1)[0]

        if file_hash not in live_hashes:
            try:
                os.remove(filepath)
                deleted_files.append(filepath)
            except Exception:
                pass

    manifest["assets"] = new_assets
    _write_manifest(manifest)

    return {
        "deleted_asset_ids": sorted(deleted_asset_ids),
        "deleted_files": sorted(deleted_files),
    }