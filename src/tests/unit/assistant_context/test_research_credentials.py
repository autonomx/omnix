from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.persistence import provider_secret_store as store
from app.research.credential_routes import register_research_credential_routes


_RESEARCH_ENV_KEYS = (
    "OMNIX_BRAVE_SEARCH_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "OMNIX_TAVILY_SEARCH_API_KEY",
    "TAVILY_API_KEY",
    "OMNIX_WEB_SEARCH_API_KEY",
)


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "provider-keys.dpapi"))
    for name in _RESEARCH_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "_protect", lambda value: b"protected:" + value[::-1])
    monkeypatch.setattr(store, "_unprotect", lambda value: value.removeprefix(b"protected:")[::-1])
    app = FastAPI()
    register_research_credential_routes(app)
    return TestClient(app)


def test_research_credential_routes_store_independent_keys_without_returning_secrets(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    initial = client.get("/api/assistant/research/credentials")
    assert initial.status_code == 200
    assert {item["provider"]: item["configured"] for item in initial.json()["providers"]} == {
        "brave": False,
        "tavily": False,
    }

    brave = client.post(
        "/api/assistant/research/credentials",
        json={"provider": "brave", "api_key": "brave-secret-1234"},
    )
    tavily = client.post(
        "/api/assistant/research/credentials",
        json={"provider": "tavily", "api_key": "tavily-secret-5678"},
    )

    assert brave.status_code == 200
    assert tavily.status_code == 200
    payload = tavily.json()
    providers = {item["provider"]: item for item in payload["providers"]}
    assert providers["brave"] == {
        "provider": "brave",
        "configured": True,
        "source": "os_protected_store",
        "editable": True,
        "key_suffix": "1234",
    }
    assert providers["tavily"] == {
        "provider": "tavily",
        "configured": True,
        "source": "os_protected_store",
        "editable": True,
        "key_suffix": "5678",
    }
    assert "brave-secret-1234" not in json.dumps(payload)
    assert "tavily-secret-5678" not in json.dumps(payload)
    assert store.load_research_provider_secrets() == {
        "brave": "brave-secret-1234",
        "tavily": "tavily-secret-5678",
    }


def test_environment_owned_research_credential_is_read_only(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("OMNIX_BRAVE_SEARCH_API_KEY", "environment-brave-9999")

    status = client.get("/api/assistant/research/credentials")
    provider = {item["provider"]: item for item in status.json()["providers"]}["brave"]
    assert provider["configured"] is True
    assert provider["source"] == "environment"
    assert provider["editable"] is False
    assert provider["key_suffix"] == "9999"
    assert "environment-brave-9999" not in status.text

    update = client.post(
        "/api/assistant/research/credentials",
        json={"provider": "brave", "api_key": "attempted-overwrite"},
    )
    assert update.status_code == 409
    assert update.json()["detail"]["code"] == "research_credential_environment_owned"
    assert store.load_research_provider_secrets()["brave"] == "environment-brave-9999"


def test_research_credential_route_can_clear_one_stored_key(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/assistant/research/credentials",
        json={"provider": "brave", "api_key": "brave-secret"},
    )
    client.post(
        "/api/assistant/research/credentials",
        json={"provider": "tavily", "api_key": "tavily-secret"},
    )

    response = client.post(
        "/api/assistant/research/credentials",
        json={"provider": "brave", "api_key": ""},
    )

    assert response.status_code == 200
    providers = {item["provider"]: item for item in response.json()["providers"]}
    assert providers["brave"]["configured"] is False
    assert providers["tavily"]["configured"] is True