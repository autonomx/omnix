from __future__ import annotations

import pytest

from app.persistence.config import (
    DatabaseConfigurationError,
    DatabaseSettings,
    database_settings,
    reset_database_settings_cache,
)


def test_database_settings_reject_sqlite() -> None:
    with pytest.raises(DatabaseConfigurationError, match="postgresql"):
        DatabaseSettings(url="sqlite:///omnix.sqlite3")


def test_database_settings_redacts_password() -> None:
    settings = DatabaseSettings(url="postgresql://omnix:secret@127.0.0.1:5432/omnix")
    assert settings.redacted_url == "postgresql://omnix:***@127.0.0.1:5432/omnix"
    assert "secret" not in settings.redacted_url


def test_database_settings_load_validated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_DATABASE_URL", "postgresql://user:pw@db.local:5433/app")
    monkeypatch.setenv("OMNIX_DATABASE_POOL_MIN", "2")
    monkeypatch.setenv("OMNIX_DATABASE_POOL_MAX", "12")
    reset_database_settings_cache()
    try:
        settings = database_settings()
        assert settings.pool_min == 2
        assert settings.pool_max == 12
        assert settings.redacted_url == "postgresql://user:***@db.local:5433/app"
    finally:
        reset_database_settings_cache()


def test_database_settings_require_an_explicit_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIX_DATABASE_URL", raising=False)
    reset_database_settings_cache()
    try:
        with pytest.raises(DatabaseConfigurationError, match="OMNIX_DATABASE_URL must be configured"):
            database_settings()
    finally:
        reset_database_settings_cache()


def test_database_settings_reject_invalid_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_DATABASE_URL", "postgresql://user:pw@db.local:5433/app")
    monkeypatch.setenv("OMNIX_DATABASE_POOL_MIN", "20")
    monkeypatch.setenv("OMNIX_DATABASE_POOL_MAX", "10")
    reset_database_settings_cache()
    try:
        with pytest.raises(DatabaseConfigurationError, match="pool_max"):
            database_settings()
    finally:
        reset_database_settings_cache()
