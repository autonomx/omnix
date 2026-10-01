import io
import secrets
import wave

import httpx
import pytest

from app import tts_http_client
from app.tts_http_client import _tts_base_url, tts_generate_stream_audio
from tests.support.http import mock_http_client


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


def test_tts_generate_stream_audio_normalizes_binary_wav(monkeypatch):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:  # an empty 8 kHz mono WAV
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
    wav = buffer.getvalue()

    def handle(request):
        assert request.headers["X-Omnix-Client"] == "gateway"
        return httpx.Response(200, headers={"content-type": "audio/wav"}, content=wav)

    monkeypatch.setattr(tts_http_client, "_http", lambda: mock_http_client(handle))

    payload = tts_generate_stream_audio(text="hello", speaker="default")

    assert payload["success"] is True
    assert payload["sample_rate"] == 8000
    assert payload["audio"]
    assert payload["chunks"] == [payload["audio"]]
