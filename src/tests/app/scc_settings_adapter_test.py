from __future__ import annotations

import json
from copy import deepcopy

from app.persistence.runtime import LegacyPersistenceRetired
from app.platform.settings_control import get_settings_payload, save_settings_payload


def test_settings_adapter_persists_profile(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    settings_file = tmp_path / "settings.json"
    secrets_file = tmp_path / "secrets.json"
    settings_file.write_text(json.dumps({"provider": "lmstudio"}), encoding="utf-8")
    secrets_file.write_text(json.dumps({"api_keys": {}}), encoding="utf-8")
    monkeypatch.setattr(shared, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(shared, "SECRETS_FILE", str(secrets_file))

    profile = get_settings_payload().settings["settings_control_center"]
    result = save_settings_payload({"base_revision": profile["revision"], "settings_profile_patch": {"global": {"providers": {"llm": "cerebras"}}}})

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert result.success is True
    assert saved["provider"] == "cerebras"
    assert saved["settings_control_center"]["global"]["providers"]["llm"] == "cerebras"


def test_settings_adapter_persists_provider_config_and_masks_secret(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    settings_file = tmp_path / "settings.json"
    secrets_file = tmp_path / "secrets.json"
    settings_file.write_text(json.dumps({"provider": "lmstudio"}), encoding="utf-8")
    secrets_file.write_text(json.dumps({"api_keys": {}}), encoding="utf-8")
    monkeypatch.setattr(shared, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(shared, "SECRETS_FILE", str(secrets_file))

    profile = get_settings_payload().settings["settings_control_center"]
    result = save_settings_payload(
        {
            "base_revision": profile["revision"],
            "provider": "openrouter",
            "openrouter": {"api_key": "sk-test-secret", "model": "openai/gpt-4o-mini"},
            "settings_profile_patch": {
                "global": {"providers": {"llm": "openrouter"}},
                "providerConfigs": {"openrouter": {"model": "openai/gpt-4o-mini"}},
            },
        }
    )

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    secrets = json.loads(secrets_file.read_text(encoding="utf-8"))
    loaded_profile = get_settings_payload().settings["settings_control_center"]
    assert result.success is True
    assert saved["provider"] == "openrouter"
    assert saved["openrouter"]["model"] == "openai/gpt-4o-mini"
    assert "api_key" not in saved["openrouter"]
    assert secrets["api_keys"]["openrouter"] == "sk-test-secret"
    assert loaded_profile["providerConfigs"]["openrouter"]["apiKey"] == "***cret"


def test_postgresql_provider_change_commits_once_without_secret_write() -> None:
    import app.shared as shared

    state = {"settings": {"provider": "lmstudio"}, "settings_writes": 0, "secret_writes": 0}

    def save_settings_callback(payload):
        state["settings"] = deepcopy(payload)
        state["settings_writes"] += 1

    def reject_secret_write(payload):
        del payload
        state["secret_writes"] += 1
        raise LegacyPersistenceRetired("environment-owned secrets")

    shared.install_postgresql_document_callbacks(
        load_settings_callback=lambda: deepcopy(state["settings"]),
        save_settings_callback=save_settings_callback,
        load_sessions_callback=lambda: {},
        save_sessions_callback=lambda payload: None,
        load_secrets_callback=lambda: {"api_keys": {}},
        save_secrets_callback=reject_secret_write,
    )
    try:
        profile = get_settings_payload().settings["settings_control_center"]
        result = save_settings_payload(
            {
                "base_revision": profile["revision"],
                "provider": "cerebras",
                "audio_provider_tts": "faster-qwen3-tts",
                "audio_provider_stt": "parakeet",
                "settings_profile_patch": {
                    "global": {"providers": {"llm": "cerebras"}},
                },
            }
        )
    finally:
        shared.clear_postgresql_document_callbacks()

    assert result.success is True
    assert state["settings_writes"] == 1
    assert state["secret_writes"] == 0
    assert state["settings"]["provider"] == "cerebras"
    assert state["settings"]["settings_control_center"]["global"]["providers"]["llm"] == "cerebras"


def test_postgresql_secret_edit_fails_before_settings_commit() -> None:
    import app.shared as shared

    original = {"provider": "lmstudio"}
    state = {"settings": deepcopy(original), "settings_writes": 0, "secret_writes": 0}

    def save_settings_callback(payload):
        state["settings"] = deepcopy(payload)
        state["settings_writes"] += 1

    def reject_secret_write(payload):
        del payload
        state["secret_writes"] += 1
        raise LegacyPersistenceRetired("environment-owned secrets")

    shared.install_postgresql_document_callbacks(
        load_settings_callback=lambda: deepcopy(state["settings"]),
        save_settings_callback=save_settings_callback,
        load_sessions_callback=lambda: {},
        save_sessions_callback=lambda payload: None,
        load_secrets_callback=lambda: {"api_keys": {}},
        save_secrets_callback=reject_secret_write,
    )
    try:
        profile = get_settings_payload().settings["settings_control_center"]
        result = save_settings_payload(
            {
                "base_revision": profile["revision"],
                "provider": "openrouter",
                "openrouter": {"api_key": "sk-new-secret", "model": "openai/gpt-4o-mini"},
                "settings_profile_patch": {
                    "global": {"providers": {"llm": "openrouter"}},
                },
            }
        )
    finally:
        shared.clear_postgresql_document_callbacks()

    assert result.success is False
    assert state["secret_writes"] == 1
    assert state["settings_writes"] == 0
    assert state["settings"] == original
