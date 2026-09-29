from __future__ import annotations

from app.persistence.document_store import PostgresDocumentStore
from app.platform import settings_control
from tests.support.settings_runtime import install_settings_test_runtime


def test_settings_adapter_persists_profile_to_typed_settings_service(monkeypatch) -> None:
    service, _secrets = install_settings_test_runtime(monkeypatch)

    def reject_document_write(*_args, **_kwargs):
        raise AssertionError("settings must not be written as a document")

    monkeypatch.setattr(PostgresDocumentStore, "write", reject_document_write)
    profile = settings_control.get_settings_payload().settings["settings_control_center"]
    result = settings_control.save_settings_payload(
        {
            "base_revision": profile["revision"],
            "settings_profile_patch": {
                "global": {"providers": {"llm": "cerebras"}},
            },
        }
    )

    assert result.success is True
    assert service.values["provider"] == "cerebras"
    assert service.values["settings_control_center"]["global"]["providers"]["llm"] == "cerebras"
    assert len(service.writes) == 1


def test_provider_config_and_secret_use_settings_and_secret_owners(monkeypatch) -> None:
    service, secret_store = install_settings_test_runtime(monkeypatch)
    profile = settings_control.get_settings_payload().settings["settings_control_center"]

    result = settings_control.save_settings_payload(
        {
            "base_revision": profile["revision"],
            "provider": "openrouter",
            "openrouter": {
                "api_key": "sk-test-secret",
                "model": "openai/gpt-4.1-mini",
            },
            "settings_profile_patch": {
                "global": {"providers": {"llm": "openrouter"}},
                "providerConfigs": {
                    "openrouter": {"model": "openai/gpt-4.1-mini"},
                },
            },
        }
    )

    assert result.success is True
    assert service.values["provider"] == "openrouter"
    assert service.values["openrouter"]["model"] == "openai/gpt-4.1-mini"
    assert secret_store["api_keys"]["openrouter"] == "sk-test-secret"
    assert service.values["openrouter"].get("api_key") is None
    displayed = settings_control.get_settings_payload().settings["openrouter"]["api_key"]
    assert displayed == "***cret"


def test_secret_write_failure_does_not_commit_settings(monkeypatch) -> None:
    service, _secrets = install_settings_test_runtime(monkeypatch)
    profile = settings_control.get_settings_payload().settings["settings_control_center"]

    def reject_secret_write(_payload):
        raise PermissionError("secret store unavailable")

    monkeypatch.setattr(settings_control, "save_secrets", reject_secret_write)
    result = settings_control.save_settings_payload(
        {
            "base_revision": profile["revision"],
            "openrouter": {"api_key": "sk-new-secret", "model": "openai/gpt-4o-mini"},
            "settings_profile_patch": {
                "global": {"providers": {"llm": "openrouter"}},
            },
        }
    )

    assert result.success is False
    assert service.writes == []
