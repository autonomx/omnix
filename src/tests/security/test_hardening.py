"""Gateway hardening: headers, rate limits, docs, SSRF, llama.cpp (WP-4.10)."""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.security.rate_limit import TokenBucket
from app.security.url_policy import UrlPolicyError, check_outbound_url


@pytest.fixture(scope="module")
def client():
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})


def test_security_headers_on_api_and_html_responses(client) -> None:
    api = client.get("/api/health")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["referrer-policy"] == "no-referrer"
    assert api.headers["x-frame-options"] == "DENY"
    assert "microphone=(self)" in api.headers["permissions-policy"]
    assert api.headers["content-security-policy"].startswith("default-src 'none'")
    assert "strict-transport-security" not in api.headers
    html = client.get("/docs")
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
    assert "default-src" not in html.headers["content-security-policy"]
    proxied = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert proxied.headers["strict-transport-security"].startswith("max-age=")


def test_token_bucket_refills_over_time() -> None:
    now = [0.0]
    bucket = TokenBucket(5, clock=lambda: now[0])
    assert [bucket.take("ip") for _ in range(5)] == [0.0] * 5
    assert bucket.take("ip") == pytest.approx(12.0)
    assert bucket.take("other") == 0.0
    now[0] = 12.0
    assert bucket.take("ip") == 0.0


def test_token_bucket_forgets_the_oldest_keys() -> None:
    bucket = TokenBucket(1, max_keys=2)
    for key in ("a", "b", "c"):
        bucket.take(key)
    assert list(bucket._buckets) == ["b", "c"]


def test_login_attempts_are_rate_limited() -> None:
    from app.gateway.main import create_gateway_app

    fresh = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    statuses = [fresh.post("/api/auth/local/login", json={"credential": "x"}).status_code for _ in range(6)]
    assert 429 not in statuses[:5]
    assert statuses[5] == 429
    limited = fresh.post("/api/auth/local/login", json={"credential": "x"})
    assert limited.json()["detail"] == {"error": "rate_limited", "limit": "login"}
    assert int(limited.headers["retry-after"]) >= 1


def test_approval_calls_are_rate_limited(monkeypatch) -> None:
    from app.gateway.main import create_gateway_app

    monkeypatch.setenv("OMNIX_APPROVAL_RATE_LIMIT_PER_MINUTE", "2")
    fresh = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"},
                       raise_server_exceptions=False)
    statuses = [fresh.post("/api/assistant/tools/proposals/p/deny", json={}).status_code for _ in range(3)]
    assert statuses[2] == 429 and 429 not in statuses[:2]


@pytest.mark.parametrize("environment,status", [("development", 200), ("production", 403)])
def test_api_docs_need_admin_docs_outside_development(monkeypatch, environment, status) -> None:
    from app.gateway.main import create_gateway_app
    from tests.support.auth import FakeAuthenticator

    monkeypatch.setenv("OMNIX_ENV", environment)
    authenticator = FakeAuthenticator()
    app = create_gateway_app(auth_service=authenticator)
    token, _ = authenticator.issue_session(user_id="user:member", roles=("member",))
    viewer = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    viewer.cookies.set("omnix_session", token)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert viewer.get(path).status_code == status, path


@pytest.mark.parametrize(
    "url,reason",
    [
        ("ftp://example.com/x", "url_scheme_not_allowed"),
        ("http://user:pw@example.com", "url_credentials_not_allowed"),
        ("http://169.254.169.254/latest/meta-data", "link_local_address_blocked"),
        ("http://[fe80::1]:8080", "link_local_address_blocked"),
        ("http://metadata.google.internal/", "metadata_host_blocked"),
        ("http://0.0.0.0:1234", "reserved_address_blocked"),
        ("http:///nohost", "url_host_required"),
    ],
)
def test_outbound_urls_that_are_always_blocked(url, reason) -> None:
    with pytest.raises(UrlPolicyError, match=reason):
        check_outbound_url(url)


def test_loopback_public_and_private_networks(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AUTH_MODE", raising=False)
    monkeypatch.delenv("OMNIX_ALLOWED_PRIVATE_NETWORKS", raising=False)
    for url in ("http://127.0.0.1:1234", "http://localhost:1234", "https://api.example.com", "http://192.168.1.20:1234"):
        check_outbound_url(url)
    # With sign-in on, private networks must be listed.
    monkeypatch.setenv("OMNIX_AUTH_MODE", "local")
    with pytest.raises(UrlPolicyError, match="private_address_not_allowed"):
        check_outbound_url("http://192.168.1.20:1234")
    monkeypatch.setenv("OMNIX_ALLOWED_PRIVATE_NETWORKS", "192.168.1.0/24")
    check_outbound_url("http://192.168.1.20:1234")
    with pytest.raises(UrlPolicyError):
        check_outbound_url("http://10.0.0.5:1234")


def test_hostnames_are_checked_at_connect_time() -> None:
    check_outbound_url("http://models.example/v1", resolve=True, resolver=lambda host, port: ["203.0.113.7"])
    with pytest.raises(UrlPolicyError, match="link_local"):
        check_outbound_url("http://rebind.example/v1", resolve=True, resolver=lambda host, port: ["169.254.169.254"])


def test_saving_a_blocked_provider_endpoint_is_refused() -> None:
    from app.platform.settings_profile_repository import SettingsProfileValidationError, save_settings_profile

    settings: dict = {}
    with pytest.raises(SettingsProfileValidationError) as refused:
        save_settings_profile(settings, {"providerConfigs": {"lmstudio": {"baseUrl": "http://169.254.169.254"}}})
    assert refused.value.errors[0]["path"] == "providerConfigs.lmstudio.baseUrl"
    save_settings_profile(settings, {"providerConfigs": {"lmstudio": {"baseUrl": "http://127.0.0.1:1235"}}})


def test_providers_refuse_blocked_endpoints_before_connecting(monkeypatch) -> None:
    import requests

    from app.providers.base import ConnectionError as ProviderConnectionError, ProviderConfig
    from app.providers.lmstudio_provider import LMStudioProvider

    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: pytest.fail("network call attempted"))
    provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url="http://169.254.169.254"))
    with pytest.raises(ProviderConnectionError, match="outbound URL policy"):
        provider._make_request("GET", "/v1/models")


def test_llamacpp_never_kills_a_foreign_process_and_confines_models(tmp_path, monkeypatch) -> None:
    from app.providers.base import ConnectionError as ProviderConnectionError, ModelNotFoundError, ProviderConfig
    from app.providers.llamacpp_provider import LlamaCppProvider

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        provider = LlamaCppProvider(ProviderConfig(provider_type="llamacpp", base_url=f"http://127.0.0.1:{port}",
                                                   extra_params={"model_dir": str(tmp_path)}))
        monkeypatch.setattr(provider, "_find_server_binary", lambda: tmp_path / "llama-server")
        monkeypatch.setattr("app.providers.llamacpp_provider.bind_host", lambda: "127.0.0.1")
        with pytest.raises(ProviderConnectionError, match="in use by another process"):
            provider._start_server(str(tmp_path / "model.gguf"))
    assert provider._stop_server() is False
    outside = tmp_path.parent / "elsewhere.gguf"
    with pytest.raises(ModelNotFoundError, match="inside the models directory"):
        provider._resolve_model_path(str(outside))
    with pytest.raises(ModelNotFoundError, match="inside the models directory"):
        provider._resolve_model_path("../elsewhere.gguf")
