from __future__ import annotations

from fastapi.testclient import TestClient

from app.assets import SharedAssetStore
from app.gateway.main import create_gateway_app


def test_gateway_saves_text_asset(tmp_path) -> None:
    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    client = TestClient(create_gateway_app(asset_store_factory=lambda: store))

    response = client.post(
        "/api/assets/story",
        json={"title": "Saved Story", "content": "# Saved Story\n\nText."},
    )

    assert response.status_code == 200
    asset = response.json()["asset"]
    assert asset["module"] == "storyteller"
    assert asset["type"] == "story"
    assert asset["id"] in {record.id for record in store.list_assets().assets}
    assert client.get(f"/api/assets/{asset['id']}/content").json()["content"] == "# Saved Story\n\nText.\n"
