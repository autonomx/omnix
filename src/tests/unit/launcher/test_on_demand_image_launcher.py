from __future__ import annotations

from app.launcher.runtime_control_app import build_runtime_service_specs


def test_launcher_starts_lightweight_image_service_without_preload(monkeypatch):
    monkeypatch.delenv("OMNIX_IMAGE_PRELOAD", raising=False)
    monkeypatch.delenv("OMNIX_IMAGE_WARMUP", raising=False)
    monkeypatch.delenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", raising=False)

    specs = {spec.service_id: spec for spec in build_runtime_service_specs()}
    image = specs["image"]
    gateway = specs["gateway"]

    assert image.enabled is True
    assert image.auto_start is True
    assert image.env["OMNIX_IMAGE_ENABLED"] == "1"
    assert image.env["OMNIX_IMAGE_PRELOAD"] == "0"
    assert image.env["OMNIX_IMAGE_WARMUP"] == "0"
    assert image.env["OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD"] == "1"
    assert image.env["OMNIX_IMAGE_URL"] == ""
    assert "app.image_service_app:app" in image.command

    assert "app.gateway.runtime_app:app" in gateway.command
    assert gateway.env["OMNIX_IMAGE_ENABLED"] == "1"
    assert gateway.env["OMNIX_IMAGE_URL"] == "http://127.0.0.1:5301"


def test_launcher_allows_explicit_preload_override(monkeypatch):
    monkeypatch.setenv("OMNIX_IMAGE_PRELOAD", "1")
    monkeypatch.setenv("OMNIX_IMAGE_WARMUP", "1")
    monkeypatch.setenv("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "0")

    specs = {spec.service_id: spec for spec in build_runtime_service_specs()}
    image = specs["image"]

    assert image.env["OMNIX_IMAGE_PRELOAD"] == "1"
    assert image.env["OMNIX_IMAGE_WARMUP"] == "1"
    assert image.env["OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD"] == "0"
