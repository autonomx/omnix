"""The TTS engine warms itself when the service starts; a call's warm-up does nothing when a voice is ready."""
from __future__ import annotations

import secrets
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.persistence.device_permits import DevicePermitUnavailable
from app.providers import faster_qwen3_tts_provider as qwen


TOKEN = secrets.token_urlsafe(32)


class FakeEngine:
    """What the service asks of an engine: whether a voice is ready, and to warm it."""

    provider_name = "faster-qwen3-tts"

    def __init__(self, ready: bool = False, fail: bool = False) -> None:
        self.ready = ready
        self.fail = fail
        self.warmed: list[tuple] = []

    def get_speakers(self):
        return [{"id": "default"}, {"id": "Jinx"}]

    def voice_ready(self, _speaker):
        return self.ready

    def warm_voice(self, speaker, language=None, *, device_permit_held=False):
        if self.fail:
            raise RuntimeError("no GPU")
        self.warmed.append((speaker, language, device_permit_held))
        return True


@pytest.fixture
def server(monkeypatch):
    from services.tts import tts_server

    previous = (tts_server._TTS_PROVIDER, tts_server._TTS_PROVIDER_NAME, tts_server._IN_FLIGHT_COUNT)
    monkeypatch.setattr(tts_server, "device_permit_slot", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(tts_server, "voice_debug_log", lambda *_args, **_kwargs: None)
    yield tts_server
    tts_server._TTS_PROVIDER, tts_server._TTS_PROVIDER_NAME, tts_server._IN_FLIGHT_COUNT = previous


def _warm_at_startup(server, engine, *, enabled: bool = True) -> None:
    with (patch("app.platform.voice.tts_runtime_state.startup_warmup_enabled", return_value=enabled),
          patch("app.platform.voice.tts_runtime_actions.configured_speaker", return_value=None),
          patch("app.platform.voice.tts_runtime_actions._has_transcript", return_value=True)):
        server._warm_loaded_engine(engine)


def test_the_service_warms_its_engine_holding_a_permit(server) -> None:
    permits: list[dict] = []
    engine = FakeEngine()

    def slot(model_class, **options):
        permits.append({"model_class": model_class, **options})
        return nullcontext()

    with patch.object(server, "device_permit_slot", slot):
        _warm_at_startup(server, engine)

    assert engine.warmed == [("Jinx", None, True)]
    # Behind live speech in the queue, which asks as "realtime".
    assert permits == [{"model_class": "tts", "priority": "interactive",
                        "timeout_seconds": server.ENGINE_WARM_PERMIT_SECONDS}]
    assert server._IN_FLIGHT_COUNT == 0


def test_the_startup_warm_up_can_be_turned_off(server) -> None:
    engine = FakeEngine()
    _warm_at_startup(server, engine, enabled=False)
    assert engine.warmed == []


def test_a_failed_startup_warm_up_leaves_the_service_running(server) -> None:
    _warm_at_startup(server, FakeEngine(fail=True))
    assert server._IN_FLIGHT_COUNT == 0


def test_an_engine_without_warm_voice_is_left_alone(server) -> None:
    _warm_at_startup(server, SimpleNamespace(provider_name="other"))


def _warm_call(server, engine, **body) -> dict:
    server._TTS_PROVIDER, server._TTS_PROVIDER_NAME = engine, "faster-qwen3-tts"
    client = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000),
                        headers={"X-Omnix-Client": "test", "X-Omnix-Service-Token": TOKEN})
    response = client.post("/api/tts/live-call/warm-voice", json={"speaker": "Jinx", **body})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", TOKEN)


def test_a_call_warm_up_does_nothing_when_the_voice_is_ready(server, token) -> None:
    def no_permit(*_args, **_kwargs):
        raise AssertionError("a ready voice must not take the GPU from a reply")

    engine = FakeEngine(ready=True)
    with patch.object(server, "device_permit_slot", no_permit):
        assert _warm_call(server, engine)["status"] == "ready"
    assert engine.warmed == []


def test_a_call_warm_up_prepares_a_voice_that_needs_it(server, token) -> None:
    engine = FakeEngine()
    assert _warm_call(server, engine, language="English")["status"] == "warmed"
    assert engine.warmed == [("Jinx", "English", True)]


def test_a_call_warm_up_gives_way_when_the_engine_is_speaking(server, token) -> None:
    class Busy:
        def __enter__(self):
            raise DevicePermitUnavailable("speaking")

        def __exit__(self, *_args):
            return False

    engine = FakeEngine()
    with patch.object(server, "device_permit_slot", lambda *_args, **_kwargs: Busy()):
        assert _warm_call(server, engine)["status"] == "busy"
    assert engine.warmed == []


def test_a_call_warm_up_never_switches_engines(server, token) -> None:
    engine = FakeEngine()
    assert _warm_call(server, engine, provider="fish-s2-pro")["status"] == "other_engine"
    assert engine.warmed == []


class _FakeModel:
    def __init__(self, *, warmed: bool, cached: bool) -> None:
        self._warmed_up = warmed
        self._voice_prompt_cache = {("jinx.wav", "Hello there.", False, False, ()): object()} if cached else {}


def _engine(monkeypatch, model):
    engine = object.__new__(qwen.FasterQwen3TTSProvider)
    engine._model_config = {}
    monkeypatch.setattr(qwen, "_clone_reference", lambda _speaker: ("jinx.wav", "Hello there."))
    monkeypatch.setattr(qwen._model_loader, "model", model)
    return engine


@pytest.mark.parametrize(("model", "ready"), [
    (None, False),
    (_FakeModel(warmed=False, cached=True), False),  # the graphs are built on the first generation
    (_FakeModel(warmed=True, cached=False), False),  # this voice's prompt is not made yet
    (_FakeModel(warmed=True, cached=True), True),
])
def test_a_voice_is_ready_once_the_graphs_and_its_prompt_are(monkeypatch, model, ready: bool) -> None:
    assert _engine(monkeypatch, model).voice_ready("Jinx") is ready


def test_warming_renders_every_live_chunk_size_to_its_end_and_only_when_needed(monkeypatch) -> None:
    engine = _engine(monkeypatch, _FakeModel(warmed=True, cached=False))
    calls: list[dict] = []
    consumed: list[int] = []

    def generate(_text, **kwargs):
        calls.append(kwargs)
        for index in range(3):
            consumed.append(index)
            yield index

    monkeypatch.setattr(engine, "generate_audio_stream", generate, raising=False)

    assert engine.warm_voice("Jinx", device_permit_held=True) is True
    assert [call["chunk_size"] for call in calls] == list(qwen._LIVE_CHUNK_SIZES)
    assert len(consumed) == 3 * len(qwen._LIVE_CHUNK_SIZES)
    assert all(call["_device_permit_held"] is True and call["append_silence"] is False for call in calls)

    monkeypatch.setattr(qwen._model_loader, "model", _FakeModel(warmed=True, cached=True))
    calls.clear()
    assert engine.warm_voice("Jinx") is False
    assert calls == []
