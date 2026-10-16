from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def server_state():
    from services.tts import tts_server

    previous = (tts_server._TTS_PROVIDER, tts_server._TTS_PROVIDER_ERROR,
                tts_server._TTS_PROVIDER_NAME, tts_server._TTS_MODEL_OWNER_GUARD)
    tts_server._TTS_MODEL_OWNER_GUARD = None
    yield tts_server
    (tts_server._TTS_PROVIDER, tts_server._TTS_PROVIDER_ERROR,
     tts_server._TTS_PROVIDER_NAME, tts_server._TTS_MODEL_OWNER_GUARD) = previous


class FakeEngine:
    def __init__(self, name, events):
        self.provider_name = name
        self.events = events

    def start(self):
        self.events.append(("start", self.provider_name))
        return {"running": True}

    def stop(self):
        self.events.append(("stop", self.provider_name))
        return True


def test_initialize_loads_the_engine_named_in_settings(server_state):
    events = []
    with (
        patch.object(server_state, "_configured_provider_name", return_value="fish-s2-pro"),
        patch.object(server_state, "_load_provider", side_effect=lambda name: FakeEngine(name, events)),
    ):
        result = server_state.initialize_tts_provider()

    assert result["ok"] is True
    assert result["provider"] == "fish-s2-pro"
    assert events == [("start", "fish-s2-pro")]


def test_initialize_tts_provider_returns_error_payload_when_provider_init_fails(server_state):
    with patch.object(server_state, "_load_provider", side_effect=TypeError("missing config")):
        result = server_state.initialize_tts_provider("faster-qwen3-tts")

    assert result["ok"] is False
    assert result["provider"] == "faster-qwen3-tts"
    assert "missing config" in result["error"]
    assert isinstance(result.get("details"), dict)


def test_health_reports_not_ready_when_provider_is_not_initialized(server_state):
    server_state._TTS_PROVIDER = None
    server_state._TTS_PROVIDER_ERROR = "provider_not_initialized"

    result = server_state.get_tts_service_status()

    assert result["ok"] is False
    assert result["provider"] == server_state._TTS_PROVIDER_NAME
    assert "provider_not_initialized" in result["error"]


def test_switching_engines_unloads_the_current_one_before_loading_the_next(server_state):
    events = []
    server_state._TTS_PROVIDER = FakeEngine("faster-qwen3-tts", events)
    server_state._TTS_PROVIDER_NAME = "faster-qwen3-tts"
    with patch.object(server_state, "_load_provider", side_effect=lambda name: FakeEngine(name, events)):
        result = server_state.select_tts_provider("fish-s2-pro")
        again = server_state.select_tts_provider("fish-s2-pro")

    assert result["ok"] is True and again["ok"] is True
    assert server_state._TTS_PROVIDER_NAME == "fish-s2-pro"
    # The second request for the serving engine changes nothing.
    assert events == [("stop", "faster-qwen3-tts"), ("start", "fish-s2-pro")]


def test_an_unknown_engine_leaves_the_current_one_loaded(server_state):
    events = []
    current = FakeEngine("faster-qwen3-tts", events)
    server_state._TTS_PROVIDER = current
    server_state._TTS_PROVIDER_NAME = "faster-qwen3-tts"

    with pytest.raises(ValueError):
        server_state.select_tts_provider("parakeet")

    assert server_state._TTS_PROVIDER is current
    assert events == []


def test_a_request_naming_the_other_engine_switches_first(server_state):
    events = []
    server_state._TTS_PROVIDER = FakeEngine("faster-qwen3-tts", events)
    server_state._TTS_PROVIDER_NAME = "faster-qwen3-tts"
    with patch.object(server_state, "_load_provider", side_effect=lambda name: FakeEngine(name, events)):
        server_state._ensure_provider("")
        server_state._ensure_provider("faster-qwen3-tts")
        assert events == []
        server_state._ensure_provider("fish-s2-pro")

    assert events == [("stop", "faster-qwen3-tts"), ("start", "fish-s2-pro")]


def test_model_owner_loss_stops_provider_and_marks_server_not_ready():
    from services.tts import tts_server

    class FakeProvider:
        stopped = False

        def stop(self):
            self.stopped = True

    provider = FakeProvider()
    guard = object()
    previous = (
        tts_server._TTS_PROVIDER,
        tts_server._TTS_PROVIDER_ERROR,
        tts_server._TTS_MODEL_OWNER_GUARD,
    )
    try:
        tts_server._TTS_PROVIDER = provider
        tts_server._TTS_PROVIDER_ERROR = ""
        tts_server._TTS_MODEL_OWNER_GUARD = guard
        tts_server._handle_tts_model_owner_loss(provider, guard)

        assert provider.stopped
        assert tts_server.get_tts_service_status()["ok"] is False
        assert "lease was lost" in tts_server.get_tts_service_status()["error"]
        assert tts_server._TTS_MODEL_OWNER_GUARD is None
    finally:
        (
            tts_server._TTS_PROVIDER,
            tts_server._TTS_PROVIDER_ERROR,
            tts_server._TTS_MODEL_OWNER_GUARD,
        ) = previous


def test_one_request_synthesizes_a_bounded_amount_of_text():
    import pydantic
    import pytest
    from services.tts import tts_server

    limit = tts_server.MAX_TTS_TEXT_CHARS
    for model in (tts_server.TtsGenerateRequest, tts_server.TtsGenerateStreamRequest):
        assert model(text="x" * limit).text == "x" * limit
        with pytest.raises(pydantic.ValidationError):
            model(text="x" * (limit + 1))
