from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.gateway.main import create_gateway_app
import app.gateway.image_asset_routes as image_asset_routes


def _store_with_asset(tmp_path, asset: AssetRecord) -> SharedAssetStore:
    store = SharedAssetStore(tmp_path / "assets.json")
    store.upsert_asset(asset)
    return store


def test_image_asset_file_is_served_by_asset_id_with_cache_headers(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "preview.png"
    image_path.write_bytes(b"PNGDATA")
    store = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:test",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_path),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assets/image:test/file")

    assert response.status_code == 200
    assert response.content == b"PNGDATA"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["content-length"] == "7"
    assert response.headers["cache-control"] == "public, max-age=300, must-revalidate"
    assert response.headers["etag"].startswith('"')
    assert response.headers["last-modified"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["accept-ranges"] == "bytes"

    cached = client.get("/api/assets/image:test/file", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert cached.content == b""

    ranged = client.get("/api/assets/image:test/file", headers={"Range": "bytes=0-2"})
    assert ranged.status_code == 206
    assert ranged.content == b"PNG"
    assert ranged.headers["content-range"] == "bytes 0-2/7"

    download = client.get("/api/assets/image:test/file?download=true")
    assert download.headers["content-disposition"].startswith("attachment")


def test_browser_preview_normalizes_transparent_png_without_changing_download(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "transparent-z-image.png"
    Image.new("RGBA", (4, 3), (220, 40, 60, 0)).save(image_path, format="PNG")
    original_bytes = image_path.read_bytes()
    store = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:z-transparent",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_path),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)
    client = TestClient(create_gateway_app())

    preview = client.get("/api/assets/image:z-transparent/file?preview=true")

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["x-omnix-image-normalized"] == "1"
    assert preview.headers["cache-control"] == "public, max-age=300, must-revalidate"
    with Image.open(BytesIO(preview.content)) as normalized:
        assert normalized.mode == "RGB"
        assert normalized.size == (4, 3)
        assert normalized.getpixel((0, 0)) == (220, 40, 60)

    download = client.get("/api/assets/image:z-transparent/file?download=true")
    assert download.status_code == 200
    assert download.content == original_bytes
    with Image.open(BytesIO(download.content)) as original:
        assert original.mode == "RGBA"
        assert original.getpixel((0, 0))[3] == 0


def test_image_asset_file_uses_direct_lookup_beyond_list_page(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "older-avatar.png"
    image_path.write_bytes(b"OLDAVATAR")
    asset = AssetRecord(
        id="image:older-avatar",
        module="characters",
        type=AssetType.IMAGE,
        mime_type="image/png",
        storage_path=str(image_path),
        created_at="2026-01-01T00:00:00+00:00",
    )

    class PaginatedStore:
        def list_assets(self):
            raise AssertionError("file delivery must not scan the paginated asset list")

        def get_asset(self, asset_id: str):
            return asset if asset_id == asset.id else None

    monkeypatch.setattr(image_asset_routes, "default_asset_store", PaginatedStore)

    response = TestClient(create_gateway_app()).get("/api/assets/image:older-avatar/file")

    assert response.status_code == 200
    assert response.content == b"OLDAVATAR"


def test_immutable_asset_uses_long_lived_cache_policy(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "map.png"
    image_path.write_bytes(b"MAP")
    store = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:immutable",
            module="rpg",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_path),
            metadata={"immutable": True},
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)

    response = TestClient(create_gateway_app()).get("/api/assets/image:immutable/file")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_image_asset_file_allows_only_trusted_svg(tmp_path, monkeypatch) -> None:
    svg_path = tmp_path / "map.svg"
    svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    untrusted = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:svg-untrusted",
            module="rpg",
            type=AssetType.IMAGE,
            mime_type="image/svg+xml",
            storage_path=str(svg_path),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: untrusted)
    client = TestClient(create_gateway_app())

    rejected = client.get("/api/assets/image:svg-untrusted/file")

    assert rejected.status_code == 415
    assert rejected.json()["detail"] == "asset_svg_not_trusted"

    trusted = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:svg-trusted",
            module="rpg",
            type=AssetType.IMAGE,
            mime_type="image/svg+xml",
            storage_path=str(svg_path),
            metadata={"trusted_svg": True, "immutable": True},
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: trusted)
    accepted = client.get("/api/assets/image:svg-trusted/file")

    assert accepted.status_code == 200
    assert accepted.headers["content-type"] == "image/svg+xml"


def test_image_asset_file_allows_legacy_curated_svg(tmp_path, monkeypatch) -> None:
    svg_path = tmp_path / "curated-map.svg"
    svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    store = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="image:legacy-curated-map",
            module="sample-world",
            type=AssetType.IMAGE,
            mime_type="image/svg+xml",
            storage_path=str(svg_path),
            compat={"source": "curated-svg"},
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)

    response = TestClient(create_gateway_app()).get("/api/assets/image:legacy-curated-map/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"


def test_image_asset_file_rejects_non_image(tmp_path, monkeypatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF")
    store = _store_with_asset(
        tmp_path,
        AssetRecord(
            id="audio:test",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path=str(audio_path),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assets/audio:test/file")

    assert response.status_code == 415
    assert response.json()["detail"] == "asset_content_not_image"
