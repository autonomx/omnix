import os

from app.runtime_services import _normalize_base_url
from app.tts_http_client import _tts_base_url


def test_normalize_base_url_strips_spaces_quotes_and_trailing_slash(monkeypatch):
    monkeypatch.setenv("OMNIX_TTS_URL", ' "http://127.0.0.1:5101/ " ')
    assert _tts_base_url() == "http://127.0.0.1:5101"


def test_runtime_services_normalize_base_url():
    assert _normalize_base_url(" 'http://127.0.0.1:5201/ ' ", "http://127.0.0.1:5201") == "http://127.0.0.1:5201"