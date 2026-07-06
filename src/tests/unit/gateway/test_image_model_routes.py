from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import image_model_routes


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(image_model_routes.router)
    return app


def test_image_model_status_proxies_service_status(monkeypatch):
    monkeypatch.setattr(
        image_model_routes,
        "get_image_service_status",
        lambda: {
            "ok": True,
            "service": "image",
            "provider": "flux_klein",
            "model": "FLUX.2 [klein] 4B",
            "loaded": False,
            "state": "unloaded",
        },
    )

    response = TestClient(_app()).get("/api/image-generation/model/status")

    assert response.status_code == 200
    assert response.json()["loaded"] is False


def test_image_model_load_and_unload_proxy_provider(monkeypatch):
    calls: list[tuple[str, str]] = []

    def load(provider: str):
        calls.append(("load", provider))
        return {"ok": True, "provider": provider, "loaded": True}

    def unload(provider: str):
        calls.append(("unload", provider))
        return {"ok": True, "provider": provider, "loaded": False, "unloaded": True}

    monkeypatch.setattr(image_model_routes, "load_image_model_via_service", load)
    monkeypatch.setattr(image_model_routes, "unload_image_model_via_service", unload)
    client = TestClient(_app())

    load_response = client.post("/api/image-generation/model/load", json={"provider": "FLUX_KLEIN"})
    unload_response = client.post("/api/image-generation/model/unload", json={"provider": "flux_klein"})

    assert load_response.status_code == 200
    assert load_response.json()["loaded"] is True
    assert unload_response.status_code == 200
    assert unload_response.json()["loaded"] is False
    assert calls == [("load", "flux_klein"), ("unload", "flux_klein")]


def test_image_model_routes_return_service_unavailable(monkeypatch):
    def fail():
        raise RuntimeError("image_service_unreachable")

    monkeypatch.setattr(image_model_routes, "get_image_service_status", fail)

    response = TestClient(_app()).get("/api/image-generation/model/status")

    assert response.status_code == 503
    assert response.json()["detail"] == "image_service_unreachable"


def test_image_model_load_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(
        image_model_routes,
        "load_image_model_via_service",
        lambda _provider: {"ok": False, "loaded": False, "error": "flux_load_failed"},
    )

    response = TestClient(_app()).post("/api/image-generation/model/load", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "flux_load_failed"
