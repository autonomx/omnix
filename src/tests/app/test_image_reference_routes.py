from __future__ import annotations

from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.assets import SharedAssetStore
from app.image.routes.references import create_image_reference_router


def test_reference_routes_list_and_upload(tmp_path, monkeypatch) -> None:
    # Manifest-backed stores only: do not read through to PostgreSQL image
    # assets that other tests in the same database created.
    monkeypatch.setattr("app.persistence.runtime.uses_postgresql_runtime", lambda: False)
    store = SharedAssetStore(tmp_path / "assets.json")
    app = FastAPI()
    app.include_router(create_image_reference_router(store))
    client = TestClient(app)

    listed_before = client.get("/api/image-generation/references")
    image_bytes = BytesIO()
    Image.new("RGB", (8, 8), (40, 80, 120)).save(image_bytes, format="PNG")
    uploaded = client.post(
        "/api/image-generation/references?filename=reference.png",
        content=image_bytes.getvalue(),
        headers={"Content-Type": "image/png"},
    )
    listed_after = client.get("/api/image-generation/references")

    assert listed_before.status_code == 200
    assert listed_before.json()["assets"] == []
    assert uploaded.status_code == 200
    assert uploaded.json()["ok"] is True
    assert uploaded.json()["asset"]["metadata"]["filename"] == "reference.png"
    assert listed_after.status_code == 200
    assert [asset["id"] for asset in listed_after.json()["assets"]] == [
        uploaded.json()["asset"]["id"]
    ]
