from __future__ import annotations

from app.persistence import provider_secret_store as store


def test_provider_keys_are_protected_and_environment_values_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store.sys, "platform", "win32")
    path = tmp_path / "provider-keys.dpapi"
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.setattr(store, "_protect", lambda value: b"protected:" + value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value.removeprefix(b"protected:")[::-1])

    store.save_provider_secrets(
        {"api_keys": {"openrouter": "or-secret", "cerebras": "cerebras-secret"}}
    )

    assert b"or-secret" not in path.read_bytes()
    assert b"cerebras-secret" not in path.read_bytes()
    assert store.load_provider_secrets() == {
        "api_keys": {"openrouter": "or-secret", "cerebras": "cerebras-secret"}
    }

    monkeypatch.setenv("CEREBRAS_API_KEY", "environment-secret")
    store.save_provider_secrets(
        {"api_keys": {"openrouter": "or-updated", "cerebras": "ignored-ui-value"}}
    )
    assert store.load_provider_secrets()["api_keys"] == {
        "openrouter": "or-updated",
        "cerebras": "environment-secret",
    }

    monkeypatch.delenv("CEREBRAS_API_KEY")
    assert store.load_provider_secrets()["api_keys"]["cerebras"] == "cerebras-secret"


def test_empty_provider_key_deletes_the_protected_value(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "provider-keys.dpapi"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.setattr(store, "_protect", lambda value: value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value[::-1])

    store.save_provider_secrets({"api_keys": {"cerebras": "secret"}})
    store.save_provider_secrets({"api_keys": {"cerebras": ""}})

    assert store.load_provider_secrets()["api_keys"]["cerebras"] == ""
