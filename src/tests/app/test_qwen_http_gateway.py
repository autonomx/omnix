import json
import secrets

import httpx
import numpy as np
import pytest

from app.providers.qwen_http_gateway import QwenHttpGatewayProvider, TtsServiceSaturated
from app.providers import service as shared
from tests.support.http import mock_http_client


@pytest.fixture(autouse=True)
def issued_service_token(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))


class _ClosingStream(httpx.SyncByteStream):
    def __init__(self, parts):
        self.parts = parts
        self.closed = False

    def __iter__(self):
        yield from self.parts

    def close(self):
        self.closed = True


def _gateway(handler):
    provider = QwenHttpGatewayProvider('http://127.0.0.1:5101/')
    provider.http = mock_http_client(handler)
    return provider


def test_streaming_pcm16_is_decoded_without_loading_a_gpu_model():
    pcm = np.array([8192, -8192] * 2500, dtype='<i2').tobytes()
    calls = []
    body = _ClosingStream((pcm[:1], pcm[1:3001], pcm[3001:]))

    def handle(request):
        calls.append(request)
        return httpx.Response(200, headers={
            'X-Omnix-Audio-Format': 'pcm_s16le',
            'X-Omnix-Sample-Rate': '24000',
            'X-Omnix-Channels': '1',
        }, stream=body)

    chunks = list(_gateway(handle).generate_audio_stream('hello', speaker='Alex', max_new_tokens=32, parity_mode=False))
    assert sum(len(audio) for audio, _, _ in chunks) == 5000
    np.testing.assert_allclose(chunks[0][0][:2], [.25, -.25])
    assert chunks[0][1] == 24000
    assert json.loads(calls[0].content) == {'text': 'hello', 'speaker': 'Alex', 'language': 'en', 'max_new_tokens': 32,
                                            'provider': 'faster-qwen3-tts'}
    assert calls[0].headers['X-Omnix-Client'] == 'gateway'
    assert str(calls[0].url).endswith('/api/tts/live-call/stream')
    assert body.closed


def test_remote_synthesis_failure_has_no_synthetic_fallback():
    gateway = _gateway(lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError, match='503'):
        list(gateway.generate_audio_stream('hello'))


def test_remote_synthesis_saturation_preserves_retry_after_without_retrying():
    calls = []
    gateway = _gateway(lambda request: calls.append(request) or httpx.Response(429, headers={'Retry-After': '2'}))
    with pytest.raises(TtsServiceSaturated) as captured:
        list(gateway.generate_audio_stream('hello'))
    assert captured.value.retry_after == '2'
    assert len(calls) == 1  # realtime: the caller decides whether to wait


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


def test_runtime_status_reports_the_remote_gpu_service():
    payload = {'ok': True, 'status': 'ready', 'details': {'runtime_status': {'model_loaded': True}}}
    provider = _gateway(lambda request: httpx.Response(200, json=payload))
    assert provider.start()['running'] is True
    assert provider.get_runtime_status()['runtime_status']['model_loaded'] is True
    assert provider.get_runtime_status()['transport'] == 'http_streaming_pcm16'
    assert provider.stop() is True


def test_an_older_tts_service_is_reported_as_needing_a_restart():
    provider = _gateway(lambda request: httpx.Response(404, json={'detail': 'Not Found'}))
    with pytest.raises(RuntimeError, match='restart the TTS service'):
        provider.resolve_generation_parameters({'temperature': 0.7})


def test_the_facade_has_the_service_serve_the_engine_it_names():
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == '/health':
            return httpx.Response(200, json={'ok': True, 'provider': 'faster-qwen3-tts'})
        if request.url.path == '/api/tts/provider':
            return httpx.Response(200, json={'ok': True, 'provider': 'fish-s2-pro'})
        return httpx.Response(200, content=b'RIFF', headers={'content-type': 'audio/wav', 'X-Omnix-Sample-Rate': '44100'})

    provider = QwenHttpGatewayProvider('http://127.0.0.1:5101', provider_name='fish-s2-pro')
    provider.http = mock_http_client(handler)

    assert provider.start()['running'] is True
    provider.generate_audio('Hello.', speaker='voice-cloning:jinx')

    assert requests[1] == ('POST', '/api/tts/provider', {'provider': 'fish-s2-pro'})
    assert requests[2][2]['provider'] == 'fish-s2-pro'


def test_an_older_tts_service_cannot_switch_engines():
    def handler(request):
        if request.url.path == '/health':
            return httpx.Response(200, json={'ok': True, 'provider': 'qwen3_tts'})
        return httpx.Response(404, json={'detail': 'Not Found'})

    provider = QwenHttpGatewayProvider('http://127.0.0.1:5101', provider_name='fish-s2-pro')
    provider.http = mock_http_client(handler)
    with pytest.raises(RuntimeError, match='restart the TTS service'):
        provider.start()


def test_gateway_http_selection_serves_the_selected_engine(monkeypatch):
    from app.providers import service as provider_service
    monkeypatch.setenv('OMNIX_GATEWAY_TTS_HTTP', '1')
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://127.0.0.1:5101')
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'fish-s2-pro'})
    monkeypatch.setattr(shared, '_tts_provider_instance', None)
    monkeypatch.setattr(shared, '_tts_provider_name', None)
    monkeypatch.setattr(shared, 'get_audio_registry', lambda: pytest.fail('constructed a local engine'))

    provider = provider_service.get_tts_provider()

    assert isinstance(provider, QwenHttpGatewayProvider)
    assert provider.provider_name == 'fish-s2-pro'
    assert provider_service.get_tts_provider('faster-qwen3-tts').provider_name == 'faster-qwen3-tts'
