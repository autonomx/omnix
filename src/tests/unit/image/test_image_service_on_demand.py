from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import image_service_app


def _status(*, loaded: bool) -> dict:
    return {
        "ok": True,
        "service": "image",
        "enabled": True,
        "provider": "flux_klein",
        "model": "FLUX.2 [klein] 4B",
        "loaded": loaded,
        "state": "loaded" if loaded else "unloaded",
        "local_model": {
            "ok": True,
            "exists": True,
            "complete": True,
            "missing": [],
            "local_dir": "resources/models/image/flux2-klein-4b",
        },
    }


def test_status_reports_unloaded_without_loading_provider(monkeypatch):
    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "get_active_image_provider_name", lambda: "flux_klein")
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(image_service_app, "_local_model_status", lambda _provider: _status(loaded=False)["local_model"])
    monkeypatch.setattr(image_service_app, "get_image_provider_cache_status", lambda: {"loaded_providers": []})

    with TestClient(image_service_app.app) as client:
        response = client.get("/provider/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "FLUX.2 [klein] 4B"
    assert payload["loaded"] is False
    assert payload["state"] == "unloaded"
    assert payload["warmed_up"] is False
    assert payload["warmup_state"] == "not_started"


def test_generate_requires_explicit_load(monkeypatch):
    generation_calls: list[dict] = []
    monkeypatch.setenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")
    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "get_active_image_provider_name", lambda: "flux_klein")
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(image_service_app, "generate_image_local", lambda payload: generation_calls.append(payload))

    with TestClient(image_service_app.app) as client:
        response = client.post("/generate", json={"prompt": "castle", "width": 768, "height": 768})

    assert response.status_code == 200
    assert response.json()["status"] == "model_unloaded"
    assert response.json()["error"] == "image_model_not_loaded"
    assert generation_calls == []


def test_load_warms_model_before_reporting_ready(monkeypatch):
    loaded = False
    warmed_up = False
    events: list[str] = []
    monkeypatch.setenv("OMNIX_IMAGE_WARMUP_ON_LOAD", "1")

    def is_loaded(_provider=None):
        return loaded

    def load_provider(provider=None):
        nonlocal loaded
        loaded = True
        events.append("load")
        return {"ok": True, "provider": provider or "flux_klein", "loaded": True}

    def warm_provider(provider=None):
        nonlocal warmed_up
        assert loaded is True
        warmed_up = True
        events.append("warmup")
        return {
            "ok": True,
            "provider": provider or "flux_klein",
            "warmed_up": True,
            "skipped": False,
            "state": "completed",
            "duration_ms": 1234,
        }

    def unload_provider(provider=None):
        nonlocal loaded, warmed_up
        loaded = False
        warmed_up = False
        events.append("unload")
        return {"ok": True, "provider": provider or "flux_klein", "loaded": False, "unloaded": True}

    def cache_status():
        runtime = {
            "flux_klein": {
                "warmed_up": warmed_up,
                "warmup_state": "completed" if warmed_up else "not_started",
                "warmup_error": "",
                "warmup_duration_ms": 1234 if warmed_up else None,
            }
        }
        return {
            "loaded_providers": ["flux_klein"] if loaded else [],
            "runtime": runtime,
        }

    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", is_loaded)
    monkeypatch.setattr(image_service_app, "load_image_provider", load_provider)
    monkeypatch.setattr(image_service_app, "warm_image_provider", warm_provider)
    monkeypatch.setattr(image_service_app, "unload_image_provider", unload_provider)
    monkeypatch.setattr(image_service_app, "_local_model_status", lambda _provider: _status(loaded=loaded)["local_model"])
    monkeypatch.setattr(image_service_app, "get_image_provider_cache_status", cache_status)

    with TestClient(image_service_app.app) as client:
        load_response = client.post("/provider/load", json={"provider": "flux_klein"})
        status_response = client.get("/provider/status")
        unload_response = client.post("/provider/unload", json={"provider": "flux_klein"})

    assert load_response.status_code == 200
    assert load_response.json()["loaded"] is True
    assert load_response.json()["warmup"]["warmed_up"] is True
    assert load_response.json()["status"]["state"] == "loaded"
    assert load_response.json()["status"]["warmed_up"] is True
    assert status_response.json()["loaded"] is True
    assert status_response.json()["warmed_up"] is True
    assert unload_response.status_code == 200
    assert unload_response.json()["loaded"] is False
    assert events == ["load", "warmup", "unload"]


def test_warmup_failure_keeps_loaded_model_available(monkeypatch):
    monkeypatch.setenv("OMNIX_IMAGE_WARMUP_ON_LOAD", "1")
    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(
        image_service_app,
        "load_image_provider",
        lambda provider=None: {"ok": True, "provider": provider or "flux_klein", "loaded": True},
    )
    monkeypatch.setattr(
        image_service_app,
        "warm_image_provider",
        lambda provider=None: {
            "ok": False,
            "provider": provider or "flux_klein",
            "warmed_up": False,
            "state": "failed",
            "error": "warmup_failed",
        },
    )
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: True)
    monkeypatch.setattr(image_service_app, "_local_model_status", lambda _provider: _status(loaded=True)["local_model"])
    monkeypatch.setattr(image_service_app, "get_image_provider_cache_status", lambda: {"loaded_providers": ["flux_klein"]})

    with TestClient(image_service_app.app) as client:
        response = client.post("/provider/load", json={"provider": "flux_klein"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["loaded"] is True
    assert response.json()["warning"] == "image_model_warmup_failed"


def test_loaded_generate_uses_real_generation_path(monkeypatch):
    monkeypatch.setenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")
    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "get_active_image_provider_name", lambda: "flux_klein")
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: True)

    def generate_image_local(payload):
        payload["_progress_callback"](16, 32, "Generating image")
        return SimpleNamespace(
            ok=True,
            provider="flux_klein",
            status="completed",
            error="",
            asset_url="/generated/image.png",
            local_path="generated/image.png",
            seed=7,
            width=768,
            height=768,
            mime_type="image/png",
            metadata={"width": 768, "height": 768},
        )

    monkeypatch.setattr(
        image_service_app,
        "generate_image_local",
        generate_image_local,
    )

    with TestClient(image_service_app.app) as client:
        response = client.post("/generate", json={"prompt": "castle", "width": 768, "height": 768, "request_id": "job:test"})
        progress_response = client.get("/generate/progress/job:test")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "completed"
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "completed"
    assert progress_response.json()["percent"] == 100


def test_generation_progress_endpoint_reports_missing_request():
    with TestClient(image_service_app.app) as client:
        response = client.get("/generate/progress/job:missing")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["status"] == "missing"
