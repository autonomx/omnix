from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.gateway import tts_runtime_actions, tts_runtime_routes, tts_runtime_state


class FakeProvider:
    provider_name = "faster-qwen3-tts"

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.stream_calls: list[dict[str, Any]] = []

    def start(self) -> dict[str, Any]:
        self.started += 1
        return {"running": True}

    def stop(self) -> bool:
        self.stopped += 1
        return True

    def get_speakers(self) -> list[dict[str, str]]:
        return [{"id": "default"}, {"id": "Jinx"}]

    def get_runtime_status(self) -> dict[str, bool]:
        return {"model_loaded": self.started > self.stopped}

    def generate_audio_stream(self, **kwargs: Any):
        self.stream_calls.append(kwargs)
        yield [0.1] * 15_360, 24_000, {"chunk_steps": 8}


def reset_state() -> None:
    with tts_runtime_state.STATE_LOCK:
        tts_runtime_state.STATE.update(
            status="idle",
            trigger=None,
            provider_class=None,
            provider_name=None,
            speaker=None,
            started_at=None,
            completed_at=None,
            duration_ms=None,
            model_loaded=False,
            graph_warmed=False,
            first_chunk_samples=None,
            sample_rate=None,
            error=None,
            warmup_count=0,
            unload_count=0,
        )


def test_warmup_loads_model_and_executes_fast_stream_chunk(monkeypatch) -> None:
    reset_state()
    provider = FakeProvider()
    monkeypatch.setattr(tts_runtime_actions, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(tts_runtime_actions, "stream_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts_runtime_state, "configured_speaker", lambda: None)

    result = tts_runtime_actions.warm_tts_runtime("test")

    assert result["status"] == "ready"
    assert result["model_loaded"] is True
    assert result["graph_warmed"] is True
    assert result["speaker"] == "Jinx"
    assert result["first_chunk_samples"] == 15_360
    assert result["sample_rate"] == 24_000
    assert provider.started == 1
    assert provider.stream_calls[0]["parity_mode"] is False
    assert provider.stream_calls[0]["max_new_tokens"] == 192
    assert provider.stream_calls[0]["chunk_size"] == 8


def test_unload_clears_provider_and_vendored_cache(monkeypatch) -> None:
    reset_state()
    provider = FakeProvider()
    provider.started = 1
    reset_calls: list[bool] = []
    monkeypatch.setattr(tts_runtime_actions, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(tts_runtime_actions, "reset_tts_model_cache", lambda: reset_calls.append(True))
    monkeypatch.setattr(tts_runtime_actions, "stream_log", lambda *args, **kwargs: None)

    result = tts_runtime_actions.unload_tts_runtime("test")

    assert result["status"] == "unloaded"
    assert result["model_loaded"] is False
    assert result["graph_warmed"] is False
    assert provider.stopped == 1
    assert reset_calls == [True]


def test_startup_warmup_env_can_enable_or_disable(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_TTS_STARTUP_WARMUP", "1")
    assert tts_runtime_state.startup_warmup_enabled() is True
    monkeypatch.setenv("OMNIX_TTS_STARTUP_WARMUP", "0")
    assert tts_runtime_state.startup_warmup_enabled() is False


def test_runtime_routes_register_once() -> None:
    app = FastAPI(title="Lifecycle Test")
    tts_runtime_routes.register_tts_runtime_routes(app)
    tts_runtime_routes.register_tts_runtime_routes(app)

    paths = [route.path for route in app.routes]
    assert paths.count("/api/tts/runtime/status") == 1
    assert paths.count("/api/tts/runtime/warmup") == 1
    assert paths.count("/api/tts/runtime/unload") == 1
