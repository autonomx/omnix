from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetListResponse, AssetRecord, AssetType
import app.gateway.image_reference_routes as routes


def test_reference_routes_list_and_upload(monkeypatch) -> None:
    asset = AssetRecord(
        id="image-reference:test",
        module="image-reference",
        type=AssetType.IMAGE,
        mime_type="image/png",
        storage_path="reference.png",
        metadata={"title": "reference.png", "width": 256, "height": 256},
        created_at="2026-07-07T00:00:00+00:00",
    )
    monkeypatch.setattr(routes, "list_image_reference_assets", lambda limit=100: AssetListResponse(assets=[asset]))
    monkeypatch.setattr(
        routes,
        "save_image_reference_upload",
        lambda data, filename, mime_type: asset,
    )

    app = FastAPI()
    routes.register_image_reference_routes(app)
    client = TestClient(app)

    listed = client.get("/api/image-generation/references")
    uploaded = client.post(
        "/api/image-generation/references?filename=reference.png",
        content=b"png-bytes",
        headers={"Content-Type": "image/png"},
    )

    assert listed.status_code == 200
    assert listed.json()["assets"][0]["id"] == asset.id
    assert uploaded.status_code == 200
    assert uploaded.json()["asset"]["id"] == asset.id
