from __future__ import annotations

from app.platform.audio_cache import invalidate_changed_audio_caches


class _Provider:
    def __init__(self) -> None:
        self.stops = 0

    def stop(self) -> None:
        self.stops += 1


def _settings() -> dict:
    return {
        "audio_provider_tts": "faster-qwen3-tts",
        "audio_provider_stt": "parakeet",
        "tts_worker_url": "http://localhost:8101",
        "stt_worker_url": "http://localhost:8102",
        "faster-qwen3-tts": {
            "model_dir": "models/tts",
            "device": "cuda",
            "dtype": "bfloat16",
            "chunk_size": 12,
        },
        "parakeet": {"base_url": "http://localhost:8000"},
    }


def test_unchanged_audio_configuration_keeps_cached_instances(monkeypatch) -> None:
    import app.shared as shared

    tts = _Provider()
    stt = _Provider()
    monkeypatch.setattr(shared, "_tts_provider_instance", tts)
    monkeypatch.setattr(shared, "_tts_provider_name", "faster-qwen3-tts")
    monkeypatch.setattr(shared, "_stt_provider_instance", stt)
    monkeypatch.setattr(shared, "_stt_provider_name", "parakeet")
    settings = _settings()

    assert invalidate_changed_audio_caches(settings, dict(settings)) == (False, False)
    assert shared._tts_provider_instance is tts
    assert shared._stt_provider_instance is stt
    assert tts.stops == 0
    assert stt.stops == 0


def test_tts_configuration_change_stops_and_clears_tts_only(monkeypatch) -> None:
    import app.shared as shared

    tts = _Provider()
    stt = _Provider()
    monkeypatch.setattr(shared, "_tts_provider_instance", tts)
    monkeypatch.setattr(shared, "_tts_provider_name", "faster-qwen3-tts")
    monkeypatch.setattr(shared, "_stt_provider_instance", stt)
    monkeypatch.setattr(shared, "_stt_provider_name", "parakeet")
    before = _settings()
    after = _settings()
    after["faster-qwen3-tts"] = {**after["faster-qwen3-tts"], "model_dir": "models/tts-v2", "chunk_size": 20}

    assert invalidate_changed_audio_caches(before, after) == (True, False)
    assert shared._tts_provider_instance is None
    assert shared._tts_provider_name is None
    assert shared._stt_provider_instance is stt
    assert tts.stops == 1
    assert stt.stops == 0


def test_stt_endpoint_change_stops_and_clears_stt_only(monkeypatch) -> None:
    import app.shared as shared

    tts = _Provider()
    stt = _Provider()
    monkeypatch.setattr(shared, "_tts_provider_instance", tts)
    monkeypatch.setattr(shared, "_tts_provider_name", "faster-qwen3-tts")
    monkeypatch.setattr(shared, "_stt_provider_instance", stt)
    monkeypatch.setattr(shared, "_stt_provider_name", "parakeet")
    before = _settings()
    after = _settings()
    after["parakeet"] = {"base_url": "http://localhost:5201"}

    assert invalidate_changed_audio_caches(before, after) == (False, True)
    assert shared._tts_provider_instance is tts
    assert shared._stt_provider_instance is None
    assert shared._stt_provider_name is None
    assert tts.stops == 0
    assert stt.stops == 1
