from __future__ import annotations

from pathlib import Path

from app.config.defaults import DEFAULT_SETTINGS
from app.settings import access as settings_access


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
