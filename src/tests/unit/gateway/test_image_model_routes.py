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


def test_image_model_status_reports_download_byte_progress(monkeypatch, tmp_path):
    model_dir = tmp_path / "z-image-turbo"
    model_dir.mkdir()
    (model_dir / "completed.safetensors").write_bytes(b"x" * 300)
    cache_dir = model_dir / ".cache" / "huggingface" / "download"
    cache_dir.mkdir(parents=True)
    (cache_dir / "next.safetensors.incomplete").write_bytes(b"x" * 200)
    (cache_dir / "metadata.json").write_bytes(b"x" * 500)

    monkeypatch.setattr(
        image_model_routes,
        "get_image_service_status",
        lambda _provider: {
            "ok": False,
            "service": "image",
            "enabled": True,
            "provider": "z_image_turbo",
            "model": "Z-Image Turbo",
            "loaded": False,
            "state": "downloading",
            "local_model": {"complete": False, "local_dir": str(model_dir)},
            "models": [],
        },
    )
    monkeypatch.setattr(
        image_model_routes,
        "_repository_total_bytes",
        lambda _provider: 1000,
    )

    response = TestClient(_app()).get(
        "/api/image-generation/model/status?provider=z_image_turbo"
    )

    assert response.status_code == 200
    progress = response.json()["download_progress"]
    assert progress["bytes_downloaded"] == 500
    assert progress["bytes_total"] == 1000
    assert progress["percent"] == 50.0
    assert progress["indeterminate"] is False


def test_download_forwards_one_time_hf_token_without_echoing_it(monkeypatch):
    calls: list[tuple[str, str]] = []

    def download(provider: str, token: str):
        calls.append((provider, token))
        return {"ok": True, "provider": provider, "loaded": False}

    monkeypatch.setattr(image_model_routes, "download_image_model_via_service", download)

    response = TestClient(_app()).post(
        "/api/image-generation/model/download",
        json={"provider": "krea2_turbo", "hf_token": "hf_secret_token"},
    )

    assert response.status_code == 200
    assert calls == [("krea2_turbo", "hf_secret_token")]
    assert "hf_secret_token" not in response.text
    assert "krea2_turbo" not in image_model_routes._DOWNLOAD_TOKENS


def test_image_service_start_uses_launcher_and_returns_ready_status(monkeypatch):
    calls: list[str] = []

    def start(provider: str):
        calls.append(provider)
        return {
            "ok": True,
            "service": "image",
            "provider": provider,
            "loaded": False,
            "state": "unloaded",
            "started": True,
        }

    monkeypatch.setattr(image_model_routes, "start_image_service_via_launcher", start)

    response = TestClient(_app()).post(
        "/api/image-generation/service/start",
        json={"provider": "Z_IMAGE_TURBO"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "unloaded"
    assert response.json()["loaded"] is False
    assert calls == ["z_image_turbo"]


def test_image_service_start_failure_is_actionable(monkeypatch):
    monkeypatch.setattr(
        image_model_routes,
        "start_image_service_via_launcher",
        lambda _provider: {
            "ok": False,
            "loaded": False,
            "state": "unavailable",
            "error": "service_disabled",
        },
    )

    response = TestClient(_app()).post(
        "/api/image-generation/service/start",
        json={"provider": "z_image_turbo"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "service_disabled"


def test_ensure_loaded_starts_service_then_loads_requested_model(monkeypatch):
    calls: list[tuple[str, str]] = []

    def start(provider: str):
        calls.append(("start", provider))
        return {"ok": True, "provider": provider, "loaded": False, "state": "unloaded"}

    def status(provider: str):
        calls.append(("status", provider))
        return {"ok": True, "provider": provider, "loaded": False, "state": "unloaded"}

    def load(provider: str):
        calls.append(("load", provider))
        return {"ok": True, "provider": provider, "loaded": True, "state": "loaded"}

    monkeypatch.setattr(image_model_routes, "start_image_service_via_launcher", start)
    monkeypatch.setattr(image_model_routes, "get_image_service_status", status)
    monkeypatch.setattr(image_model_routes, "load_image_model_via_service", load)

    response = TestClient(_app()).post(
        "/api/image-generation/model/ensure-loaded",
        json={"provider": "image:flux_klein"},
    )

    assert response.status_code == 200
    assert response.json()["loaded"] is True
    assert calls == [
        ("start", "flux_klein"),
        ("status", "flux_klein"),
        ("load", "flux_klein"),
    ]


def test_ensure_loaded_skips_duplicate_model_load(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        image_model_routes,
        "start_image_service_via_launcher",
        lambda provider: calls.append(("start", provider)) or {
            "ok": True,
            "provider": provider,
            "loaded": True,
        },
    )
    monkeypatch.setattr(
        image_model_routes,
        "get_image_service_status",
        lambda provider: calls.append(("status", provider)) or {
            "ok": True,
            "provider": provider,
            "loaded": True,
            "state": "loaded",
        },
    )
    monkeypatch.setattr(
        image_model_routes,
        "load_image_model_via_service",
        lambda _provider: (_ for _ in ()).throw(AssertionError("already loaded model must not reload")),
    )

    response = TestClient(_app()).post(
        "/api/image-generation/model/ensure-loaded",
        json={"provider": "flux_klein"},
    )

    assert response.status_code == 200
    assert response.json()["loaded"] is True
    assert calls == [("start", "flux_klein"), ("status", "flux_klein")]


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


def test_unavailable_runtime_preserves_downloaded_flux_status(monkeypatch):
    def fail():
        raise RuntimeError("image_service_unreachable")

    monkeypatch.setattr(image_model_routes, "get_image_service_status", fail)
    monkeypatch.setattr(image_model_routes, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(
        image_model_routes,
        "get_image_local_model_status",
        lambda provider: {
            "ok": provider == "flux_klein",
            "exists": provider == "flux_klein",
            "complete": provider == "flux_klein",
            "missing": [] if provider == "flux_klein" else ["model_index.json"],
            "local_dir": f"resources/models/image/{provider}",
        },
    )

    response = TestClient(_app()).get(
        "/api/image-generation/model/status?provider=flux_klein"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "unavailable"
    assert payload["downloaded"] is True
    assert payload["local_model"]["complete"] is True
    assert payload["local_model"]["local_dir"].endswith("flux_klein")


def test_image_model_status_returns_structured_unavailable_payload(monkeypatch):
    def fail():
        raise RuntimeError("image_service_unreachable")

    monkeypatch.setattr(image_model_routes, "get_image_service_status", fail)
    monkeypatch.setattr(image_model_routes, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(
        image_model_routes,
        "get_image_local_model_status",
        lambda provider: {
            "ok": False,
            "exists": False,
            "complete": False,
            "missing": ["model_index.json"],
            "local_dir": f"resources/models/image/{provider}",
        },
    )

    response = TestClient(_app()).get("/api/image-generation/model/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["enabled"] is True
    assert payload["loaded"] is False
    assert payload["state"] == "unavailable"
    assert payload["error"] == "image_service_unreachable"


def test_image_model_load_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(
        image_model_routes,
        "load_image_model_via_service",
        lambda _provider: {"ok": False, "loaded": False, "error": "flux_load_failed"},
    )

    response = TestClient(_app()).post("/api/image-generation/model/load", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "flux_load_failed"
