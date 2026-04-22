def test_image_settings_get_route(client):
    res = client.get("/api/image/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert isinstance(data["settings"], dict)


def test_image_runtime_route(client):
    res = client.get("/api/image/runtime")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data


def test_image_provider_unload_all_route(client):
    res = client.post("/api/image/provider/unload_all")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
