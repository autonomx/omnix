from __future__ import annotations

from app import image_http_client


def test_start_image_service_uses_launcher_then_waits_for_status(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LAUNCHER_URL", "http://127.0.0.1:5055")

    def request_json(method: str, url: str, payload, timeout: float):
        calls.append((method, url))
        return {"ok": True, "service": {"id": "image", "status": "running"}}

    monkeypatch.setattr(image_http_client, "_request_json", request_json)
    monkeypatch.setattr(
        image_http_client,
        "get_image_service_status",
        lambda provider: {
            "ok": True,
            "service": "image",
            "provider": provider,
            "loaded": False,
            "state": "unloaded",
        },
    )

    result = image_http_client.start_image_service_via_launcher("z_image_turbo")

    assert calls == [("POST", "http://127.0.0.1:5055/api/services/image/start")]
    assert result["ok"] is True
    assert result["provider"] == "z_image_turbo"
    assert result["state"] == "unloaded"
    assert result["loaded"] is False
    assert result["started"] is True


def test_start_image_service_reports_launcher_disabled_state(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setattr(
        image_http_client,
        "_request_json",
        lambda *_args, **_kwargs: {"ok": False, "error": "service_disabled"},
    )

    result = image_http_client.start_image_service_via_launcher("flux_klein")

    assert result["ok"] is False
    assert result["state"] == "unavailable"
    assert result["error"] == "service_disabled"


def test_image_service_url_defaults_to_local_runtime_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.delenv("OMNIX_IMAGE_URL", raising=False)

    assert image_http_client._image_service_url() == "http://127.0.0.1:5301"
