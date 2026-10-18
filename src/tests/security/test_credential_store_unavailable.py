"""An unreadable credential store is a 503 with a recovery hint, never a half-applied save."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.trading import execution_api, market_data_api
from app.composition.gateway import settings_control
from app.errors import install_error_envelope
from app.platform.research.api import create_research_credential_router
from app.security import provider_secret_store as store
from tests.support.settings_runtime import install_settings_test_runtime


def _unavailable(*_args, **_kwargs):
    raise store.ProviderSecretStoreUnavailable("the protected credential store cannot be decrypted")


def _client(router) -> TestClient:
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(router)
    return TestClient(app)


def _assert_store_unavailable(response, tmp_path) -> None:
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "credential_store_unavailable"
    assert body["detail"]["code"] == "credential_store_unavailable"
    assert str(tmp_path / "secrets.dpapi") in body["detail"]["hint"]


@pytest.fixture()
def secrets_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "secrets.dpapi"))
    return tmp_path


def test_alpaca_credentials(secrets_path, monkeypatch) -> None:
    monkeypatch.setattr(execution_api, "save_trading_provider_secrets", _unavailable)
    monkeypatch.setattr(execution_api.sys, "platform", "win32")
    client = _client(execution_api.create_trading_execution_router())
    response = client.put("/api/trading/execution/providers/alpaca-iex/credentials", json={"api_key_id": "PK1"})
    _assert_store_unavailable(response, secrets_path)


def test_coinmarketcap_credentials(secrets_path, monkeypatch) -> None:
    monkeypatch.setattr(market_data_api, "save_trading_provider_secrets", _unavailable)
    monkeypatch.setattr(market_data_api.sys, "platform", "win32")
    client = _client(market_data_api.create_trading_market_data_router())
    response = client.put("/api/trading/market-data/providers/coinmarketcap/credentials", json={"api_key": "k"})
    _assert_store_unavailable(response, secrets_path)


def test_research_credentials(secrets_path, monkeypatch) -> None:
    monkeypatch.setattr(store.sys, "platform", "win32")
    for name in ("OMNIX_BRAVE_SEARCH_API_KEY", "BRAVE_SEARCH_API_KEY", "OMNIX_WEB_SEARCH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "save_research_provider_secret", _unavailable)
    client = _client(create_research_credential_router())
    response = client.post("/api/assistant/research/credentials", json={"provider": "brave", "api_key": "b"})
    _assert_store_unavailable(response, secrets_path)


def test_settings_save_stops_before_any_setting_is_written(secrets_path, monkeypatch) -> None:
    service, _secrets = install_settings_test_runtime(monkeypatch)
    monkeypatch.setattr(settings_control, "save_secrets", _unavailable)
    invalidated: list[bool] = []
    monkeypatch.setattr(settings_control, "invalidate_provider_cache", lambda: invalidated.append(True))
    profile = settings_control.get_settings_payload().settings["settings_control_center"]
    with pytest.raises(store.ProviderSecretStoreUnavailable):
        settings_control.save_settings_payload(
            {
                "base_revision": profile["revision"],
                "provider": "openrouter",
                "openrouter": {"api_key": "sk-new", "model": "openai/gpt-4o-mini"},
                "settings_profile_patch": {"global": {"providers": {"llm": "openrouter"}}},
            }
        )
    assert service.writes == [] and invalidated == []


def test_editing_one_provider_key_never_deletes_another(secrets_path, monkeypatch) -> None:
    """The lenient read came back empty (store busy); the strict patch keeps cerebras."""
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(store, "_protect", lambda value: b"protected:" + value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value.removeprefix(b"protected:")[::-1])
    for name in ("OPENROUTER_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    store.save_provider_secrets({"api_keys": {"openrouter": "or-old", "cerebras": "cb-keep"}})

    install_settings_test_runtime(monkeypatch, secrets={"api_keys": {"openrouter": "", "cerebras": ""}})
    monkeypatch.setattr(settings_control, "save_secrets", store.save_provider_secrets)
    profile = settings_control.get_settings_payload().settings["settings_control_center"]
    result = settings_control.save_settings_payload(
        {
            "base_revision": profile["revision"],
            "openrouter": {"api_key": "or-new"},
            "settings_profile_patch": {"global": {"providers": {"llm": "openrouter"}}},
        }
    )
    assert result.success is True
    assert store.load_provider_secrets()["api_keys"] == {"openrouter": "or-new", "cerebras": "cb-keep"}


def test_save_provider_secrets_patches_only_named_providers(secrets_path, monkeypatch) -> None:
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(store, "_protect", lambda value: value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value[::-1])
    for name in ("OPENROUTER_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    store.save_provider_secrets({"api_keys": {"openrouter": "a", "cerebras": "b"}})
    store.save_provider_secrets({"api_keys": {"openrouter": "c"}})
    assert store.load_provider_secrets()["api_keys"] == {"openrouter": "c", "cerebras": "b"}
    store.save_provider_secrets({"api_keys": {"cerebras": ""}})  # explicit deletion
    assert store.load_provider_secrets()["api_keys"] == {"openrouter": "c", "cerebras": ""}


def test_lenient_reads_do_not_wait_for_a_writer(secrets_path, monkeypatch) -> None:
    import threading
    import time

    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(store, "_protect", lambda value: value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value[::-1])
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    store.save_provider_secrets({"api_keys": {"cerebras": "b"}})
    held = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with store.payload_lock():
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    held.wait(5)
    started = time.monotonic()
    found = []
    reader = threading.Thread(target=lambda: found.append(store.load_provider_secrets()["api_keys"]["cerebras"]))
    reader.start()
    reader.join(2)
    elapsed = time.monotonic() - started
    release.set()
    holder.join()
    assert found == ["b"] and elapsed < 1.5
