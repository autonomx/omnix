"""Global image asset store (IMG-4)."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, Any

ASSET_DIR = os.path.join("resources", "data", "generated_images")
MANIFEST_PATH = os.path.join(ASSET_DIR, "manifest.json")


def _ensure_dirs():
    os.makedirs(ASSET_DIR, exist_ok=True)


def _load_manifest() -> Dict[str, Any]:
    if not os.path.isfile(MANIFEST_PATH):
        return {"assets": {}}
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"assets": {}}


def _save_manifest(data: Dict[str, Any]):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def save_image_asset_bytes(image_bytes: bytes, mime_type: str, asset_id: str, metadata: Dict[str, Any]):
    _ensure_dirs()
    manifest = _load_manifest()

    content_hash = _hash_bytes(image_bytes)
    filename = f"{asset_id}_{content_hash}.png"
    path = os.path.join(ASSET_DIR, filename)

    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(image_bytes)

    manifest["assets"][asset_id] = {
        "path": path,
        "mime_type": mime_type,
        "hash": content_hash,
        "metadata": metadata,
    }

    _save_manifest(manifest)
    return path


def register_image_asset_file(file_path: str, asset_id: str, metadata: Dict[str, Any]):
    _ensure_dirs()
    manifest = _load_manifest()

    manifest["assets"][asset_id] = {
        "path": file_path,
        "mime_type": "image/png",
        "hash": "",
        "metadata": metadata,
    }

    _save_manifest(manifest)
    return file_path


def get_image_asset_manifest():
    return _load_manifest()


def cleanup_unused_image_assets():
    manifest = _load_manifest()
    existing = set()

    for v in manifest["assets"].values():
        existing.add(v.get("path"))

    for fname in os.listdir(ASSET_DIR):
        full = os.path.join(ASSET_DIR, fname)
        if full not in existing and fname != "manifest.json":
            try:
                os.remove(full)
            except Exception:
                pass

    return {"ok": True}
