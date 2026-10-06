import secrets

import pytest

from app.providers.tts_http_client import _tts_base_url


@pytest.fixture(autouse=True)
def issued_service_token(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))


def test_tts_endpoint_rejects_embedded_quotes_and_whitespace(monkeypatch):
    monkeypatch.setenv("OMNIX_TTS_URL", ' "http://127.0.0.1:5101/ " ')
    with pytest.raises(ValueError, match='Service URLs'):
        _tts_base_url()


def test_tts_endpoint_uses_bound_process_config(monkeypatch):
    from app.runtime.config import RuntimeConfig, ServiceEndpoint, install_runtime_config
    install_runtime_config(RuntimeConfig(tts=ServiceEndpoint('http://localhost:5101/')))
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://other:5201')
    assert _tts_base_url() == 'http://localhost:5101'
