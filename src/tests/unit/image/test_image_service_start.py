from __future__ import annotations

from app import image_http_client


def test_start_image_service_uses_launcher_then_lightweight_readiness_probe(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    readiness_attempts = 0
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LAUNCHER_URL", "http://127.0.0.1:5055")
    monkeypatch.setenv("OMNIX_IMAGE_URL", "http://127.0.0.1:5301")

    def request_json(method: str, url: str, payload, timeout: float):
        nonlocal readiness_attempts
        calls.append((method, url))
        if url.endswith("/openapi.json"):
            readiness_attempts += 1
            if readiness_attempts == 1:
                raise RuntimeError("unreachable:service stopped")
            return {"openapi": "3.1.0"}
        if url.endswith("/api/services/image/start"):
            return {"ok": True, "service": {"id": "image", "status": "running"}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(image_http_client, "_request_json", request_json)
    monkeypatch.setattr(
        image_http_client,
        "get_image_service_status",
        lambda _provider: (_ for _ in ()).throw(
            AssertionError("startup must not perform full provider status validation")
        ),
    )

    result = image_http_client.start_image_service_via_launcher("z_image_turbo")

    assert calls == [
        ("GET", "http://127.0.0.1:5301/openapi.json"),
        ("POST", "http://127.0.0.1:5055/api/services/image/start"),
        ("GET", "http://127.0.0.1:5301/openapi.json"),
    ]
    assert result["ok"] is True
    assert result["provider"] == "z_image_turbo"
    assert result["state"] == "unloaded"
    assert result["loaded"] is False
    assert result["started"] is True


def test_start_image_service_skips_launcher_when_runtime_is_already_ready(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LAUNCHER_URL", "http://127.0.0.1:5055")
    monkeypatch.setenv("OMNIX_IMAGE_URL", "http://127.0.0.1:5301")

    def request_json(method: str, url: str, payload, timeout: float):
        calls.append((method, url))
        if url.endswith("/openapi.json"):
            return {"openapi": "3.1.0"}
        raise AssertionError("launcher must not be called for an already-ready service")

    monkeypatch.setattr(image_http_client, "_request_json", request_json)

    result = image_http_client.start_image_service_via_launcher("flux_klein")

    assert calls == [("GET", "http://127.0.0.1:5301/openapi.json")]
    assert result["ok"] is True
    assert result["already_running"] is True
    assert result["started"] is False


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
