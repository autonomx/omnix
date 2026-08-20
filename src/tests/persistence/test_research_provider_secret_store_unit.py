from __future__ import annotations

from app.persistence import provider_secret_store as store


_RESEARCH_ENV_KEYS = (
    "OMNIX_BRAVE_SEARCH_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "OMNIX_TAVILY_SEARCH_API_KEY",
    "TAVILY_API_KEY",
    "OMNIX_WEB_SEARCH_API_KEY",
)


def _prepare_windows_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "provider-keys.dpapi"))
    for name in _RESEARCH_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "_protect", lambda value: b"protected:" + value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value.removeprefix(b"protected:")[::-1])


def test_research_provider_keys_are_independent_and_dpapi_protected(tmp_path, monkeypatch) -> None:
    _prepare_windows_store(tmp_path, monkeypatch)
    path = store.provider_secret_path()

    store.save_research_provider_secret("brave", "brave-secret-1234")
    store.save_research_provider_secret("tavily", "tavily-secret-5678")

    raw = path.read_bytes()
    assert b"brave-secret-1234" not in raw
    assert b"tavily-secret-5678" not in raw
    assert store.load_research_provider_secrets() == {
        "brave": "brave-secret-1234",
        "tavily": "tavily-secret-5678",
    }
    assert store.research_provider_credential_source("brave") == "os_protected_store"
    assert store.research_provider_credential_source("tavily") == "os_protected_store"
    assert store.research_provider_credential_editable("brave") is True
    assert store.research_provider_credential_editable("tavily") is True


def test_research_provider_specific_environment_keys_are_authoritative(tmp_path, monkeypatch) -> None:
    _prepare_windows_store(tmp_path, monkeypatch)
    store.save_research_provider_secret("brave", "stored-brave")
    store.save_research_provider_secret("tavily", "stored-tavily")

    monkeypatch.setenv("OMNIX_BRAVE_SEARCH_API_KEY", "environment-brave")
    monkeypatch.setenv("TAVILY_API_KEY", "environment-tavily")

    store.save_research_provider_secret("brave", "ignored-brave")
    store.save_research_provider_secret("tavily", "ignored-tavily")

    assert store.load_research_provider_secrets() == {
        "brave": "environment-brave",
        "tavily": "environment-tavily",
    }
    assert store.research_provider_credential_source("brave") == "environment"
    assert store.research_provider_credential_source("tavily") == "environment"
    assert store.research_provider_credential_editable("brave") is False
    assert store.research_provider_credential_editable("tavily") is False


def test_legacy_shared_search_key_remains_compatible_but_is_identified(tmp_path, monkeypatch) -> None:
    _prepare_windows_store(tmp_path, monkeypatch)
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "legacy-shared-key")

    assert store.load_research_provider_secrets() == {
        "brave": "legacy-shared-key",
        "tavily": "legacy-shared-key",
    }
    assert store.research_provider_credential_source("brave") == "legacy_environment"
    assert store.research_provider_credential_source("tavily") == "legacy_environment"
    assert store.research_provider_credential_editable("brave") is False


def test_empty_research_provider_key_clears_only_that_provider(tmp_path, monkeypatch) -> None:
    _prepare_windows_store(tmp_path, monkeypatch)
    store.save_research_provider_secret("brave", "brave-secret")
    store.save_research_provider_secret("tavily", "tavily-secret")

    store.save_research_provider_secret("brave", "")

    assert store.load_research_provider_secrets() == {
        "brave": "",
        "tavily": "tavily-secret",
    }