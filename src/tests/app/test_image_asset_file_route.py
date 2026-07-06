from __future__ import annotations

from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.gateway.main import create_gateway_app
import app.gateway.image_asset_routes as image_asset_routes


def test_image_asset_file_is_served_by_asset_id(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "preview.png"
    image_path.write_bytes(b"PNG")
    store = SharedAssetStore(tmp_path / "assets.json")
    store.upsert_asset(
        AssetRecord(
            id="image:test",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_path),
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assets/image:test/file")

    assert response.status_code == 200
    assert response.content == b"PNG"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline")

    download = client.get("/api/assets/image:test/file?download=true")
    assert download.headers["content-disposition"].startswith("attachment")


def test_image_asset_file_rejects_non_image(tmp_path, monkeypatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF")
    store = SharedAssetStore(tmp_path / "assets.json")
    store.upsert_asset(
        AssetRecord(
            id="audio:test",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path=str(audio_path),
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assets/audio:test/file")

    assert response.status_code == 415
    assert response.json()["detail"] == "asset_content_not_image"
