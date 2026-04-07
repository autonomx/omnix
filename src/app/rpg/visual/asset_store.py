"""Phase 12.10 — Asset file store for generated images."""
from __future__ import annotations

from pathlib import Path


_ASSET_DIR = Path("data/rpg_generated_assets")


def ensure_asset_dir() -> Path:
    """Ensure the asset directory exists and return its path."""
    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    return _ASSET_DIR


def build_asset_filename(asset_id: str, mime_type: str) -> str:
    """Build a safe filename from asset ID and MIME type."""
    ext = ".png"
    if mime_type == "image/jpeg":
        ext = ".jpg"
    safe_id = "".join(ch for ch in str(asset_id) if ch.isalnum() or ch in {"-", "_", ":"})
    return f"{safe_id}{ext}"


def save_asset_bytes(asset_id: str, image_bytes: bytes, mime_type: str) -> str:
    """Save image bytes to the asset directory and return the path."""
    directory = ensure_asset_dir()
    filename = build_asset_filename(asset_id, mime_type)
    path = directory / filename
    path.write_bytes(image_bytes)
    return str(path)