from __future__ import annotations

import io

import pytest

Image = pytest.importorskip("PIL.Image")

from app.assets import SharedAssetStore
from app.image.reference_assets import (
    close_image_references,
    list_image_reference_assets,
    load_image_reference_assets,
    save_image_reference_upload,
)


def _png_bytes(width: int = 640, height: int = 480) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "navy").save(buffer, format="PNG")
    return buffer.getvalue()


def test_reference_upload_is_saved_as_reusable_image_asset(tmp_path) -> None:
    store = SharedAssetStore(tmp_path / "assets.json")

    asset = save_image_reference_upload(
        _png_bytes(),
        filename="hero-reference.png",
        mime_type="image/png",
        store=store,
        root=tmp_path / "references",
    )

    assert asset.id.startswith("image-reference:")
    assert asset.module == "image-reference"
    assert asset.mime_type == "image/png"
    assert asset.metadata["title"] == "hero-reference.png"
    assert asset.metadata["width"] == 640
    assert asset.metadata["height"] == 480
    assert list_image_reference_assets(store=store).assets == [asset]

    images = load_image_reference_assets([asset.id], store=store)
    try:
        assert len(images) == 1
        assert images[0].size == (640, 480)
        assert images[0].mode == "RGB"
    finally:
        close_image_references(images)


def test_reference_upload_is_downscaled_to_safe_edge(tmp_path) -> None:
    store = SharedAssetStore(tmp_path / "assets.json")

    asset = save_image_reference_upload(
        _png_bytes(2048, 1024),
        filename="wide.png",
        mime_type="image/png",
        store=store,
        root=tmp_path / "references",
    )

    assert asset.metadata["width"] == 1024
    assert asset.metadata["height"] == 512
