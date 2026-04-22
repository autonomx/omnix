def test_image_providers_route(client):
    res = client.get("/api/image/providers")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert isinstance(data["providers"], list)
    keys = {item["key"] for item in data["providers"]}
    assert "flux_klein" in keys
    assert "mock" in keys
