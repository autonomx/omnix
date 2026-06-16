from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_start_all_disables_image_service_by_default() -> None:
    script = (_repo_root() / "start_all.bat").read_text(encoding="utf-8")

    assert 'if not defined OMNIX_IMAGE_ENABLED set "OMNIX_IMAGE_ENABLED=0"' in script
    assert 'if not defined OMNIX_START_IMAGE_SERVICE set "OMNIX_START_IMAGE_SERVICE=0"' in script
    assert 'set "OMNIX_IMAGE_URL="' in script
    assert "The launcher will not start image service" in script
    assert "OMNIX_IMAGE_ENABLED=1" in script
    assert "OMNIX_START_IMAGE_SERVICE=1" in script


def test_start_all_does_not_import_diffusers_during_default_app_startup() -> None:
    script = (_repo_root() / "start_all.bat").read_text(encoding="utf-8")

    assert "[APP][FLUX] diffusers OK" not in script
    assert 'import diffusers; print' not in script
    assert 'if /I "%OMNIX_IMAGE_ENABLED%"=="1" if /I "%OMNIX_START_IMAGE_SERVICE%"=="1"' in script

    service_manager = (_repo_root() / "src" / "app" / "launcher" / "service_manager.py").read_text(encoding="utf-8")
    assert '"OMNIX_IMAGE_PRELOAD": "1"' in service_manager
    assert '"OMNIX_IMAGE_WARMUP": "1"' in service_manager
    assert 'service_id="image"' in service_manager


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


def test_rpg_image_generation_policy_defaults_disabled() -> None:
    from app.rpg.media.image_generation_policy import build_rpg_image_generation_policy

    policy = build_rpg_image_generation_policy({})

    assert policy["enabled"] is False
    assert policy["startup_service_allowed"] is False
    assert policy["runtime_provider_allowed"] is False
    assert policy["preload_allowed"] is False
    assert policy["warmup_allowed"] is False
    assert policy["default_provider_when_disabled"] == "mock"
    assert policy["simulation_authority"] is False
    assert policy["presentation_only"] is True


def test_rpg_image_generation_policy_requires_explicit_startup_opt_in() -> None:
    from app.rpg.media.image_generation_policy import build_rpg_image_generation_policy, is_rpg_image_generation_enabled

    enabled_only = build_rpg_image_generation_policy({"OMNIX_IMAGE_ENABLED": "1"})
    full_start = build_rpg_image_generation_policy({"OMNIX_IMAGE_ENABLED": "1", "OMNIX_START_IMAGE_SERVICE": "1"})

    assert is_rpg_image_generation_enabled({"OMNIX_IMAGE_ENABLED": "1"}) is True
    assert enabled_only["enabled"] is True
    assert enabled_only["startup_service_allowed"] is False
    assert full_start["startup_service_allowed"] is True
