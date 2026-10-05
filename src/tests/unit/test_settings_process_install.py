"""Model services install the PostgreSQL-backed settings themselves (TTS and image servers)."""
from __future__ import annotations

import pytest

from app.settings import access
from app.settings.service import SettingsService


@pytest.fixture(autouse=True)
def _clean_service():
    access.reset_settings_service_for_tests()
    yield
    access.reset_settings_service_for_tests()


def test_a_model_service_process_installs_settings_from_its_database():
    database = object()
    service = access.install_database_settings_service(database)
    assert isinstance(service, SettingsService)
    assert service.database is database
    assert access.current_settings_service() is service
    # The core specs are registered, so reads fall back to their defaults.
    assert "faster-qwen3-tts" in service.specs


def test_installing_again_keeps_the_existing_service():
    first = access.install_database_settings_service(object())
    assert access.install_database_settings_service(object()) is first


def test_the_tts_and_image_servers_install_it_at_startup():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert "install_database_settings_service(default_database())" in (root / "src/tts_server.py").read_text(encoding="utf-8")
    assert "install_database_settings_service(database)" in (root / "src/app/image_service_runtime.py").read_text(encoding="utf-8")
