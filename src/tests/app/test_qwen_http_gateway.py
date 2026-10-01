from types import SimpleNamespace

import numpy as np
import pytest
import secrets

from app.providers.qwen_http_gateway import QwenHttpGatewayProvider, TtsServiceSaturated
from app.providers import service as shared


@pytest.fixture(autouse=True)
def issued_service_token(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))


def test_streaming_pcm16_is_decoded_without_loading_a_gpu_model(monkeypatch):
    pcm = np.array([8192, -8192] * 2500, dtype='<i2').tobytes()
    calls = []
    class Response:
        status_code = 200
        headers = {
            'X-Omnix-Audio-Format': 'pcm_s16le',
            'X-Omnix-Sample-Rate': '24000',
            'X-Omnix-Channels': '1',
        }
        closed = False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            assert chunk_size == 4800
            return iter((pcm[:1], pcm[1:3001], pcm[3001:]))

        def close(self):
            self.closed = True

    response = Response()
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.post', post)
    chunks = list(QwenHttpGatewayProvider('http://127.0.0.1:5101/').generate_audio_stream('hello', speaker='Alex', max_new_tokens=32, parity_mode=False))
    assert sum(len(audio) for audio, _, _ in chunks) == 5000
    np.testing.assert_allclose(chunks[0][0][:2], [.25, -.25])
    assert chunks[0][1] == 24000
    assert calls[0][1]['json'] == {'text': 'hello', 'speaker': 'Alex', 'language': 'en', 'max_new_tokens': 32}
    assert calls[0][1]['headers']['X-Omnix-Client'] == 'gateway'
    assert calls[0][0].endswith('/api/tts/live-call/stream')
    assert calls[0][1]['stream'] is True
    assert response.closed


def test_remote_synthesis_failure_has_no_synthetic_fallback(monkeypatch):
    import requests

    response = SimpleNamespace(
        status_code=503,
        headers={},
        raise_for_status=lambda: (_ for _ in ()).throw(requests.HTTPError('service unavailable')),
        close=lambda: None,
    )
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.post', lambda *args, **kwargs: response)
    with pytest.raises(requests.HTTPError, match='service unavailable'):
        list(QwenHttpGatewayProvider('http://127.0.0.1:5101').generate_audio_stream('hello'))


def test_remote_synthesis_saturation_preserves_retry_after(monkeypatch):
    response = SimpleNamespace(
        status_code=429,
        headers={'Retry-After': '2'},
        raise_for_status=lambda: None,
        close=lambda: None,
    )
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.post', lambda *args, **kwargs: response)
    with pytest.raises(TtsServiceSaturated) as captured:
        list(QwenHttpGatewayProvider('http://127.0.0.1:5101').generate_audio_stream('hello'))
    assert captured.value.retry_after == '2'


def test_gateway_http_selection_does_not_construct_local_provider(monkeypatch):
    from app.providers import service as provider_service
    monkeypatch.setenv('OMNIX_GATEWAY_TTS_HTTP', '1')
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://127.0.0.1:5101')
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'faster-qwen3-tts'})
    monkeypatch.setattr(shared, '_tts_provider_instance', None)
    monkeypatch.setattr(shared, '_tts_provider_name', None)
    def forbidden():
        raise AssertionError('Local registry must not initialize for the shared GPU service')
    monkeypatch.setattr(shared, 'get_audio_registry', forbidden)
    first = provider_service.get_tts_provider()
    assert isinstance(first, QwenHttpGatewayProvider)
    assert provider_service.get_tts_provider() is first
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://127.0.0.1:5102')
    assert provider_service.get_tts_provider() is not first


def test_http_selection_requires_explicit_service_url(monkeypatch):
    from app.providers import service as provider_service
    monkeypatch.setenv('OMNIX_GATEWAY_TTS_HTTP', '1')
    monkeypatch.delenv('OMNIX_TTS_URL', raising=False)
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'faster-qwen3-tts'})
    with pytest.raises(ValueError, match='OMNIX_TTS_URL'):
        provider_service.get_tts_provider()


def test_api_cannot_bypass_local_tts_capability_with_another_provider(monkeypatch):
    from app.providers import service as provider_service
    from app.runtime.config import RuntimeConfig, GatewayRole, install_runtime_config
    install_runtime_config(RuntimeConfig(gateway_role=GatewayRole.API))
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'another-local-provider'})
    monkeypatch.setattr(shared, 'get_audio_registry', lambda: pytest.fail('API constructed a local provider'))
    monkeypatch.setattr(shared, '_tts_provider_instance', object())
    monkeypatch.setattr(shared, '_tts_provider_name', 'another-local-provider')
    with pytest.raises(RuntimeError, match='run_local_tts'):
        provider_service.get_tts_provider()


def test_runtime_status_reports_the_remote_gpu_service(monkeypatch):
    payload = {'ok': True, 'status': 'ready', 'details': {'runtime_status': {'model_loaded': True}}}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.get', lambda *args, **kwargs: response)
    provider = QwenHttpGatewayProvider('http://127.0.0.1:5101')
    assert provider.start()['running'] is True
    assert provider.get_runtime_status()['runtime_status']['model_loaded'] is True
    assert provider.get_runtime_status()['transport'] == 'http_streaming_pcm16'
    assert provider.stop() is True
