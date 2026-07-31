from __future__ import annotations

from fastapi.testclient import TestClient

from app import image_service_app


def test_download_does_not_load_selected_model(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(
        image_service_app,
        "download_image_model",
        lambda provider: calls.append(("download", provider)) or {
            "ok": True,
            "provider": provider,
            "loaded": False,
        },
    )
    monkeypatch.setattr(
        image_service_app,
        "load_image_provider",
        lambda provider=None: calls.append(("load", provider or "flux_klein")),
    )
    monkeypatch.setattr(
        image_service_app,
        "_local_model_status",
        lambda provider: {
            "ok": provider == "krea2_turbo",
            "exists": provider == "krea2_turbo",
            "complete": provider == "krea2_turbo",
            "missing": [],
            "local_dir": f"resources/models/image/{provider}",
        },
    )

    with TestClient(image_service_app.app) as client:
        response = client.post(
            "/provider/download",
            json={"provider": "krea2_turbo"},
        )

    assert response.status_code == 200
    assert response.json()["loaded"] is False
    assert calls == [("download", "krea2_turbo")]
