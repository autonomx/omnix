from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_start_all_disables_image_service_by_default() -> None:
    script = (_repo_root() / "start_all.bat").read_text(encoding="utf-8")

    assert 'if not defined OMNIX_IMAGE_ENABLED set "OMNIX_IMAGE_ENABLED=0"' in script
    assert 'if not defined OMNIX_START_IMAGE_SERVICE set "OMNIX_START_IMAGE_SERVICE=0"' in script
    assert 'set "OMNIX_IMAGE_URL="' in script
    assert "[IMAGE SERVICE] Skipped" in script
    assert "OMNIX_IMAGE_ENABLED=1" in script
    assert "OMNIX_START_IMAGE_SERVICE=1" in script


def test_start_all_does_not_import_diffusers_during_default_app_startup() -> None:
    script = (_repo_root() / "start_all.bat").read_text(encoding="utf-8")

    assert "[APP][FLUX] diffusers OK" not in script
    assert 'import diffusers; print' not in script
    assert "OMNIX_IMAGE_PRELOAD=1" in script
    assert "OMNIX_IMAGE_WARMUP=1" in script
    assert 'if /I "%OMNIX_IMAGE_ENABLED%"=="1" if /I "%OMNIX_START_IMAGE_SERVICE%"=="1"' in script


def test_image_config_defaults_to_mock_when_disabled(monkeypatch) -> None:
    from app.image import config

    monkeypatch.delenv("OMNIX_IMAGE_ENABLED", raising=False)
    assert config.is_image_generation_enabled() is False
    assert config.get_active_image_provider_name() == "mock"


def test_image_config_allows_flux_when_explicitly_enabled(monkeypatch) -> None:
    from app.image import config

    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    assert config.is_image_generation_enabled() is True
    assert config.get_active_image_provider_name() in {"flux_klein", "mock"}


def test_image_service_app_skips_preload_unless_enabled() -> None:
    source = (_repo_root() / "src" / "app" / "image_service_app.py").read_text(encoding="utf-8")

    assert "Image generation disabled; skipping provider preload and warmup" in source
    assert 'os.environ.get("OMNIX_IMAGE_PRELOAD", "0")' in source
    assert 'os.environ.get("OMNIX_IMAGE_WARMUP", "0")' in source
    assert 'return {"ok": False, "provider": "disabled", "error": "image_generation_disabled"}' in source
