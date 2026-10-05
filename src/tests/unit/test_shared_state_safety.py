from __future__ import annotations

from pathlib import Path

import pytest

from app.config.defaults import DEFAULT_SETTINGS
from app.runtime.tenant_context import local_tenant_context
from app.settings import access as settings_access
from app.settings.registry import core_setting_specs
from app.settings.service import SettingsService


class _UnavailableConnection:
    def __enter__(self):
        raise ConnectionError("settings database unavailable")

    def __exit__(self, *_args):
        return False


class _UnavailableDatabase:
    def connection(self):
        return _UnavailableConnection()


def test_default_settings_are_deep_copied_without_shared_module() -> None:
    settings_access.reset_settings_service_for_tests()

    first = settings_access.load_settings(allow_defaults_without_service=True)
    first["lmstudio"]["base_url"] = "http://mutated.invalid"
    first["image"]["flux_klein"]["width"] = 1

    second = settings_access.load_settings(allow_defaults_without_service=True)

    assert second["lmstudio"]["base_url"] == "http://localhost:1234"
    assert second["image"]["flux_klein"]["width"] == 768
    assert DEFAULT_SETTINGS["lmstudio"]["base_url"] == "http://localhost:1234"
    assert DEFAULT_SETTINGS["image"]["flux_klein"]["width"] == 768


def test_shared_module_is_retired() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    assert not (root / "shared.py").exists()


def test_settings_reads_fail_closed_when_database_is_unavailable() -> None:
    settings_access.reset_settings_service_for_tests()
    settings_access.install_settings_service(
        SettingsService(
            _UnavailableDatabase(),
            local_tenant_context,
            specs=core_setting_specs(),
        )
    )
    try:
        with pytest.raises(ConnectionError, match="settings database unavailable"):
            settings_access.load_settings()
    finally:
        settings_access.reset_settings_service_for_tests()
