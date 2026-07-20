from __future__ import annotations

from app.providers.audio_plugins import (
    DEFAULT_PARAKEET_BASE_URL,
    ParakeetSTT,
    _parakeet_base_url,
)


def test_legacy_gateway_url_migrates_to_dedicated_stt_service(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_STT_URL", raising=False)

    assert _parakeet_base_url({"base_url": "http://localhost:8000"}) == DEFAULT_PARAKEET_BASE_URL
    assert _parakeet_base_url({"base_url": "http://127.0.0.1:8000"}) == DEFAULT_PARAKEET_BASE_URL


def test_stt_environment_url_overrides_stale_saved_setting(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_STT_URL", "http://127.0.0.1:6201/transcribe")

    assert _parakeet_base_url({"base_url": "http://localhost:8000"}) == "http://127.0.0.1:6201"


def test_transcribe_posts_to_dedicated_parakeet_route(tmp_path, monkeypatch) -> None:
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"audio")
    captured: dict[str, str] = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"success": True, "text": "A working transcript.", "segments": []}

    def fake_post(url: str, **kwargs):
        del kwargs
        captured["url"] = url
        return _Response()

    monkeypatch.delenv("OMNIX_STT_URL", raising=False)
    monkeypatch.setattr("app.providers.audio_plugins.requests.post", fake_post)

    result = ParakeetSTT(config={"base_url": "http://localhost:8000"}).transcribe(str(sample))

    assert captured["url"] == "http://127.0.0.1:5201/transcribe"
    assert result["success"] is True
    assert result["text"] == "A working transcript."
