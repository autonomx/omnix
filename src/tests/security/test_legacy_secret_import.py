from __future__ import annotations

import json

import pytest

from app.errors import LegacyPersistenceRetired
from app.security import legacy_secret_import


def test_imports_credentials_without_overwriting_protected_store(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "secrets.json"
    source.write_text(
        json.dumps(
            {
                "api_keys": {"openrouter": "legacy-key", "unknown": "ignored"},
                "research_api_keys": {"brave": "legacy-search-key"},
                "trading_credentials": {
                    "alpaca_iex": {"api_key_id": "legacy-account", "secret_key": "legacy-secret"}
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(legacy_secret_import.sys, "platform", "win32")
    monkeypatch.setattr(
        legacy_secret_import.provider_secret_store,
        "_stored_payload_for_import",
        lambda: {"api_keys": {"openrouter": "protected-key"}},
    )
    written = {}
    monkeypatch.setattr(
        legacy_secret_import.provider_secret_store,
        "_write_payload",
        lambda payload: written.update(payload),
    )

    count, archive = legacy_secret_import.import_legacy_secrets(source)

    assert count == 3
    assert archive == tmp_path / "secrets.json.imported"
    assert archive.read_text(encoding="utf-8")
    assert not source.exists()
    assert written["api_keys"]["openrouter"] == "protected-key"
    assert written["api_keys"].get("unknown") is None
    assert written["research_api_keys"]["brave"] == "legacy-search-key"
    assert written["trading_credentials"]["alpaca_iex"]["secret_key"] == "legacy-secret"


def test_import_requires_windows_protected_store_before_reading_source(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "secrets.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(legacy_secret_import.sys, "platform", "linux")

    with pytest.raises(LegacyPersistenceRetired, match="Windows protected store"):
        legacy_secret_import.import_legacy_secrets(source)

    assert source.exists()


def test_import_refuses_to_replace_existing_archive(tmp_path, monkeypatch) -> None:
    source = tmp_path / "secrets.json"
    source.write_text(json.dumps({"api_keys": {"cerebras": "legacy"}}), encoding="utf-8")
    (tmp_path / "secrets.json.imported").write_text("archived", encoding="utf-8")
    monkeypatch.setattr(legacy_secret_import.sys, "platform", "win32")

    with pytest.raises(FileExistsError, match="archive already exists"):
        legacy_secret_import.import_legacy_secrets(source)

    assert source.exists()


def test_import_keeps_plaintext_source_when_protected_store_is_unreadable(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "secrets.json"
    source.write_text(json.dumps({"api_keys": {"cerebras": "legacy"}}), encoding="utf-8")
    monkeypatch.setattr(legacy_secret_import.sys, "platform", "win32")

    def unreadable_store() -> dict[str, object]:
        raise LegacyPersistenceRetired("existing provider credential store is unreadable")

    monkeypatch.setattr(
        legacy_secret_import.provider_secret_store,
        "_stored_payload_for_import",
        unreadable_store,
    )

    with pytest.raises(LegacyPersistenceRetired, match="unreadable"):
        legacy_secret_import.import_legacy_secrets(source)

    assert source.exists()
    assert not (tmp_path / "secrets.json.imported").exists()
