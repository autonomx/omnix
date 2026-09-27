import io
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from app.providers.qwen_http_gateway import QwenHttpGatewayProvider


def test_pcm16_wav_is_decoded_without_loading_a_gpu_model(monkeypatch):
    data = io.BytesIO()
    with wave.open(data, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(np.array([8192, -8192] * 2500, dtype='<i2').tobytes())
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(content=data.getvalue(), headers={'content-type': 'audio/wav'}, raise_for_status=lambda: None)
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.post', post)
    chunks = list(QwenHttpGatewayProvider('http://127.0.0.1:5101/').generate_audio_stream('hello', speaker='Alex', max_new_tokens=32, parity_mode=False))
    assert sum(len(audio) for audio, _, _ in chunks) == 5000
    np.testing.assert_allclose(chunks[0][0][:2], [.25, -.25])
    assert chunks[0][1] == 24000
    assert calls[0][1]['json'] == {'text': 'hello', 'speaker': 'Alex', 'language': 'en', 'max_new_tokens': 32}


def test_remote_synthesis_failure_has_no_synthetic_fallback(monkeypatch):
    response = SimpleNamespace(headers={'content-type': 'application/json'}, raise_for_status=lambda: None,
                               json=lambda: {'success': True, 'is_fallback': True, 'audio': ''})
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.post', lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match='real synthesized audio'):
        list(QwenHttpGatewayProvider('http://127.0.0.1:5101').generate_audio_stream('hello'))


def test_gateway_http_selection_does_not_construct_local_provider(monkeypatch):
    from app import shared
    monkeypatch.setenv('OMNIX_GATEWAY_TTS_HTTP', '1')
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://127.0.0.1:5101')
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'faster-qwen3-tts'})
    monkeypatch.setattr(shared, '_tts_provider_instance', None)
    monkeypatch.setattr(shared, '_tts_provider_name', None)
    def forbidden():
        raise AssertionError('Local registry must not initialize for the shared GPU service')
    monkeypatch.setattr(shared, 'get_audio_registry', forbidden)
    first = shared.get_tts_provider()
    assert isinstance(first, QwenHttpGatewayProvider)
    assert shared.get_tts_provider() is first
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://127.0.0.1:5102')
    assert shared.get_tts_provider() is not first


def test_http_selection_requires_explicit_service_url(monkeypatch):
    from app import shared
    monkeypatch.setenv('OMNIX_GATEWAY_TTS_HTTP', '1')
    monkeypatch.delenv('OMNIX_TTS_URL', raising=False)
    monkeypatch.setattr(shared, 'load_settings', lambda: {'audio_provider_tts': 'faster-qwen3-tts'})
    with pytest.raises(ValueError, match='OMNIX_TTS_URL'):
        shared.get_tts_provider()


def test_runtime_status_reports_the_remote_gpu_service(monkeypatch):
    payload = {'ok': True, 'status': 'ready', 'details': {'runtime_status': {'model_loaded': True}}}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr('app.providers.qwen_http_gateway.requests.get', lambda *args, **kwargs: response)
    provider = QwenHttpGatewayProvider('http://127.0.0.1:5101')
    assert provider.start()['running'] is True
    assert provider.get_runtime_status()['runtime_status']['model_loaded'] is True
    assert provider.get_runtime_status()['transport'] == 'http_buffered_wav'
    assert provider.stop() is True
