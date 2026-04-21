from types import SimpleNamespace

from app.runtime_services import _normalize_base_url
from app.tts_http_client import _tts_base_url, tts_generate_stream_audio


def test_normalize_base_url_strips_spaces_quotes_and_trailing_slash(monkeypatch):
    monkeypatch.setenv("OMNIX_TTS_URL", ' "http://127.0.0.1:5101/ " ')
    assert _tts_base_url() == "http://127.0.0.1:5101"


def test_runtime_services_normalize_base_url():
    assert _normalize_base_url(" 'http://127.0.0.1:5201/ ' ", "http://127.0.0.1:5201") == "http://127.0.0.1:5201"


def test_tts_generate_stream_audio_normalizes_binary_wav(monkeypatch):
    def fake_post(*args, **kwargs):
        return SimpleNamespace(
            headers={"content-type": "audio/wav"},
            content=b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("app.tts_http_client.requests.post", fake_post)

    payload = tts_generate_stream_audio(text="hello", speaker="default")

    assert payload["success"] is True
    assert payload["sample_rate"] == 8000
    assert payload["audio"]
    assert payload["chunks"] == [payload["audio"]]
