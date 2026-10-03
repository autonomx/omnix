"""The Settings Control Center saves through /api/settings/profile (WP-9.3 regression).

POST /api/settings became a typed per-key patch in Phase 2, which left the
control center's profile save (profile patch, provider sections and API keys)
without a route.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.platform.settings_profile_core import SETTINGS_PROFILE_KEY
from tests.support.settings_runtime import install_settings_test_runtime


def _client() -> TestClient:
    return TestClient(create_gateway_app(), base_url="http://127.0.0.1:8000", headers={"X-Omnix-Client": "test"})


def test_profile_read_masks_api_keys(monkeypatch) -> None:
    install_settings_test_runtime(monkeypatch, secrets={"api_keys": {"openrouter": "or-secret-1234"}})

    payload = _client().get("/api/settings/profile").json()

    profile = payload["settings"][SETTINGS_PROFILE_KEY]
    assert profile["revision"]
    assert "or-secret-1234" not in str(payload)
    assert profile["providerConfigs"]["openrouter"]["apiKey"].startswith("***")


def test_profile_save_patches_the_profile_and_routes_keys_to_the_secret_store(monkeypatch) -> None:
    service, secrets = install_settings_test_runtime(monkeypatch, secrets={"api_keys": {"openrouter": "or-secret-1234"}})
    client = _client()
    revision = client.get("/api/settings/profile").json()["settings"][SETTINGS_PROFILE_KEY]["revision"]

    response = client.post("/api/settings/profile", json={
        "base_revision": revision,
        "settings_profile_patch": {"global": {"providers": {"llm": "openrouter"}}},
        "provider": "openrouter",
        "openrouter": {"api_key": "or-secret-5678", "model": "anthropic/claude-sonnet"},
    })

    assert response.status_code == 200 and response.json() == {"success": True}
    assert secrets["api_keys"]["openrouter"] == "or-secret-5678"
    assert service.values["provider"] == "openrouter"
    assert service.values["openrouter"]["model"] == "anthropic/claude-sonnet"
    assert service.values[SETTINGS_PROFILE_KEY]["global"]["providers"]["llm"] == "openrouter"


def test_a_masked_key_leaves_the_stored_key_alone(monkeypatch) -> None:
    _service, secrets = install_settings_test_runtime(monkeypatch, secrets={"api_keys": {"openrouter": "or-secret-1234"}})

    _client().post("/api/settings/profile", json={"openrouter": {"api_key": "***1234", "model": "x"}})

    assert secrets["api_keys"]["openrouter"] == "or-secret-1234"


def test_a_stale_base_revision_is_refused(monkeypatch) -> None:
    install_settings_test_runtime(monkeypatch)

    response = _client().post("/api/settings/profile", json={
        "base_revision": "stale-revision",
        "settings_profile_patch": {"global": {"providers": {"llm": "openrouter"}}},
    })

    assert response.json() == {"success": False}


def test_unknown_fields_are_rejected(monkeypatch) -> None:
    install_settings_test_runtime(monkeypatch)

    assert _client().post("/api/settings/profile", json={"surprise": 1}).status_code == 422
