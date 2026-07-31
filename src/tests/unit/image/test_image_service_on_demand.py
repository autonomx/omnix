from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import image_service_app
from app.image import lifecycle, service
from app.image.models import ImageGenerationRequest
from app.image.providers.base import ImageGenerationResult


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
    monkeypatch.setattr(
        image_service_app,
        "_local_model_status",
        lambda _provider: _status(loaded=False)["local_model"],
    )
    monkeypatch.setattr(image_service_app, "get_image_provider_cache_status", lambda: {"loaded_providers": []})

    with TestClient(image_service_app.app) as client:
        response = client.get("/provider/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "FLUX.2 [klein] 4B"
    assert payload["loaded"] is False
    assert payload["state"] == "unloaded"


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


def test_load_and_unload_routes_report_final_residency(monkeypatch):
    loaded = False

    def is_loaded(_provider=None):
        return loaded

    def load_provider(provider=None):
        nonlocal loaded
        loaded = True
        return {"ok": True, "provider": provider or "flux_klein", "loaded": True}

    def unload_provider(provider=None):
        nonlocal loaded
        loaded = False
        return {"ok": True, "provider": provider or "flux_klein", "loaded": False, "unloaded": True}

    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", is_loaded)
    monkeypatch.setattr(image_service_app, "load_image_provider", load_provider)
    monkeypatch.setattr(image_service_app, "unload_image_provider", unload_provider)
    monkeypatch.setattr(
        image_service_app,
        "_local_model_status",
        lambda _provider: _status(loaded=loaded)["local_model"],
    )
    monkeypatch.setattr(
        image_service_app,
        "get_image_provider_cache_status",
        lambda: {"loaded_providers": ["flux_klein"] if loaded else []},
    )

    with TestClient(image_service_app.app) as client:
        load_response = client.post("/provider/load", json={"provider": "flux_klein"})
        status_response = client.get("/provider/status")
        unload_response = client.post("/provider/unload", json={"provider": "flux_klein"})

    assert load_response.status_code == 200
    assert load_response.json()["loaded"] is True
    assert status_response.json()["loaded"] is True
    assert unload_response.status_code == 200
    assert unload_response.json()["loaded"] is False


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
        response = client.post(
            "/generate",
            json={"prompt": "castle", "width": 768, "height": 768, "request_id": "job:test"},
        )
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


def test_provider_defaults_are_model_specific():
    expected = {
        "flux_klein": (4, 1.0),
        "krea2_turbo": (8, 0.0),
        "z_image_turbo": (9, 0.0),
    }
    for provider_name, (steps, guidance) in expected.items():
        request = ImageGenerationRequest(provider=provider_name, prompt="city")
        payload = service._map_to_provider_payload(request, {})
        assert payload["num_inference_steps"] == steps
        assert payload["guidance_scale"] == guidance


def test_local_generation_requires_explicit_load_without_creating_provider(monkeypatch):
    monkeypatch.setenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")
    monkeypatch.setattr(service, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(
        service,
        "get_or_create_image_provider",
        lambda _provider=None: (_ for _ in ()).throw(AssertionError("provider must not be created")),
    )

    result = service.generate_image_local({
        "provider": "krea2_turbo",
        "prompt": "city",
        "width": 768,
        "height": 768,
        "no_cache": True,
    })

    assert result.ok is False
    assert result.status == "model_unloaded"
    assert result.error == "image_model_not_loaded"


def test_unload_after_generation_releases_selected_provider(monkeypatch):
    unloaded: list[str] = []

    class FakeProvider:
        def generate(self, payload):
            return ImageGenerationResult(
                ok=True,
                status="completed",
                file_path="generated/test.png",
                asset_url="/generated/test.png",
                metadata={"steps": payload["num_inference_steps"]},
            )

    provider = FakeProvider()
    monkeypatch.setenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")
    monkeypatch.setattr(service, "is_image_provider_loaded", lambda _provider=None: True)
    monkeypatch.setattr(service, "get_cached_provider", lambda _provider=None: provider)
    monkeypatch.setattr(service, "unload_image_provider", lambda name=None: unloaded.append(name or ""))

    result = service.generate_image_local({
        "provider": "krea2_turbo",
        "prompt": "city",
        "width": 768,
        "height": 768,
        "no_cache": True,
        "unload_after_generation": True,
    })

    assert result.ok is True
    assert unloaded == ["krea2_turbo"]
    assert result.metadata["unloaded_after_generation"] is True


def test_atomic_load_switch_keeps_only_one_resident_provider(monkeypatch):
    providers: dict[str, object] = {}
    failures: list[Exception] = []

    class FakeProvider:
        def __init__(self, name: str):
            self.name = name
            self.loaded = False

        def load(self):
            time.sleep(0.02)
            self.loaded = True

        def unload(self):
            self.loaded = False

        def is_loaded(self):
            return self.loaded

    def build_provider(name: str):
        provider = FakeProvider(name)
        providers[name] = provider
        return provider

    monkeypatch.setattr(lifecycle, "_PROVIDER_CACHE", {})
    monkeypatch.setattr(lifecycle, "_build_provider", build_provider)
    monkeypatch.setattr(lifecycle, "_validate_load_budget", lambda _provider: None)

    def load(name: str):
        try:
            lifecycle.load_image_provider(name)
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [
        threading.Thread(target=load, args=("flux_klein",)),
        threading.Thread(target=load, args=("krea2_turbo",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert sum(bool(getattr(provider, "loaded", False)) for provider in providers.values()) == 1
    cache = lifecycle.get_image_provider_cache_status()
    assert len(cache["loaded_providers"]) == 1
    assert len(cache["cached_providers"]) == 1
