from __future__ import annotations

import threading
import time
from typing import Any

from app.gateway import live_voice_execution_lane as execution_lane
from app.gateway.live_voice_execution_lane import (
    PriorityTtsScheduler,
    TtsLanePriority,
    live_voice_execution_lane_config,
    reset_live_voice_execution_lane_for_tests,
    resolve_live_voice_chat_route,
    resolve_live_voice_tts_provider,
)


class _BlockingProvider:
    provider_name = "test-live-tts"

    def __init__(self) -> None:
        self.speculative_started = threading.Event()
        self.release_speculative = threading.Event()
        self.calls: list[str] = []
        self.kwargs_by_text: dict[str, dict[str, Any]] = {}

    def generate_audio_stream(self, *, text: str, **kwargs):
        self.calls.append(text)
        self.kwargs_by_text[text] = dict(kwargs)
        if text == "speculative":
            self.speculative_started.set()
            self.release_speculative.wait(timeout=2)
        yield b"\x01\x00", 24_000, {"text": text}


class _DedicatedProvider:
    def start(self):
        return {"running": True}


class _DedicatedRegistry:
    def __init__(self) -> None:
        self.calls = 0
        self.provider = _DedicatedProvider()

    def create_tts_provider(self, _provider_name: str, *, config):
        self.calls += 1
        assert isinstance(config, dict)
        return self.provider


def test_dedicated_chat_route_is_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_PROVIDER_ID", "lmstudio")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "qwen-live-fast")

    config = live_voice_execution_lane_config()
    assert config.dedicated_chat_enabled is True
    assert resolve_live_voice_chat_route("session-provider", "session-model") == (
        "lmstudio",
        "qwen-live-fast",
        "dedicated",
    )


def test_session_route_remains_default(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_VOICE_PROVIDER_ID", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_VOICE_MODEL_ID", raising=False)

    assert resolve_live_voice_chat_route("session-provider", "session-model") == (
        "session-provider",
        "session-model",
        "session",
    )


def test_dedicated_tts_reuses_started_provider_without_reloading_settings(monkeypatch) -> None:
    reset_live_voice_execution_lane_for_tests()
    monkeypatch.setenv("OMNIX_LIVE_TTS_DEDICATED", "true")
    monkeypatch.setenv("OMNIX_LIVE_TTS_PROVIDER_NAME", "faster-qwen3-tts")
    registry = _DedicatedRegistry()
    settings_calls = 0

    def load_settings():
        nonlocal settings_calls
        settings_calls += 1
        return {"faster-qwen3-tts": {"device": "cuda"}}

    monkeypatch.setattr(execution_lane.shared, "load_settings", load_settings)
    monkeypatch.setattr(execution_lane, "get_audio_registry", lambda: registry)

    try:
        first, first_lane = resolve_live_voice_tts_provider(object())
        second, second_lane = resolve_live_voice_tts_provider(object())

        assert first is registry.provider
        assert second is first
        assert first_lane == second_lane == "dedicated"
        assert settings_calls == 1
        assert registry.calls == 1
    finally:
        reset_live_voice_execution_lane_for_tests()


def test_speculative_tts_uses_one_step_hidden_chunk_without_changing_accepted_shape(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", raising=False)
    provider = _BlockingProvider()
    scheduler = PriorityTtsScheduler(log=lambda *_args, **_kwargs: None)

    provider.release_speculative.set()
    list(
        scheduler.stream(
            provider,
            text="speculative",
            speaker=None,
            language="en",
            kwargs={"chunk_size": 4, "temperature": 0.6},
            priority=TtsLanePriority.SPECULATIVE,
        )
    )
    list(
        scheduler.stream(
            provider,
            text="accepted",
            speaker=None,
            language="en",
            kwargs={"chunk_size": 4, "temperature": 0.6},
            priority=TtsLanePriority.ACCEPTED,
        )
    )

    assert provider.kwargs_by_text["speculative"]["chunk_size"] == 1
    assert provider.kwargs_by_text["accepted"]["chunk_size"] == 4
    assert provider.kwargs_by_text["speculative"]["temperature"] == 0.6


def test_speculative_tts_chunk_override_remains_available(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", "2")
    provider = _BlockingProvider()
    scheduler = PriorityTtsScheduler(log=lambda *_args, **_kwargs: None)

    provider.release_speculative.set()
    list(
        scheduler.stream(
            provider,
            text="speculative",
            speaker=None,
            language="en",
            kwargs={"chunk_size": 4},
            priority=TtsLanePriority.SPECULATIVE,
        )
    )

    assert provider.kwargs_by_text["speculative"]["chunk_size"] == 2


def test_promoted_speculative_ticket_keeps_authoritative_chunk_shape() -> None:
    provider = _BlockingProvider()
    provider.release_speculative.set()
    promotion = threading.Event()
    promotion.set()
    scheduler = PriorityTtsScheduler(log=lambda *_args, **_kwargs: None)

    list(
        scheduler.stream(
            provider,
            text="speculative",
            speaker=None,
            language="en",
            kwargs={"chunk_size": 4},
            priority=TtsLanePriority.SPECULATIVE,
            promotion_event=promotion,
        )
    )

    assert provider.kwargs_by_text["speculative"]["chunk_size"] == 4


def test_accepted_tts_preempts_active_speculative_stream_and_reports_wait() -> None:
    logs: list[tuple[str, dict[str, Any]]] = []
    scheduler = PriorityTtsScheduler(
        log=lambda _stream_id, _source, event, **fields: logs.append((event, fields))
    )
    provider = _BlockingProvider()
    speculative_output: list[tuple[bytes, int, object]] = []
    accepted_output: list[tuple[bytes, int, object]] = []

    speculative = threading.Thread(
        target=lambda: speculative_output.extend(
            scheduler.stream(
                provider,
                text="speculative",
                speaker=None,
                language="en",
                kwargs={"chunk_size": 4},
                priority=TtsLanePriority.SPECULATIVE,
            )
        ),
    )
    speculative.start()
    assert provider.speculative_started.wait(timeout=1)

    accepted = threading.Thread(
        target=lambda: accepted_output.extend(
            scheduler.stream(
                provider,
                text="accepted",
                speaker=None,
                language="en",
                kwargs={"chunk_size": 4},
                priority=TtsLanePriority.ACCEPTED,
            )
        ),
    )
    accepted.start()

    deadline = time.time() + 1
    while time.time() < deadline:
        if scheduler.snapshot()["active_cancelled"]:
            break
        time.sleep(0.005)
    assert scheduler.snapshot()["active_cancelled"] is True

    provider.release_speculative.set()
    speculative.join(timeout=1)
    accepted.join(timeout=1)

    assert speculative_output == []
    assert accepted_output == [(b"\x01\x00", 24_000, {"text": "accepted"})]
    assert provider.calls == ["speculative", "accepted"]
    assert provider.kwargs_by_text["speculative"]["chunk_size"] == 1
    assert provider.kwargs_by_text["accepted"]["chunk_size"] == 4

    events = [event for event, _fields in logs]
    assert "speculative_tts_preempt_requested" in events
    assert events.count("tts_lane_ticket_enqueued") == 2
    assert events.count("tts_lane_ticket_acquired") == 2
    assert events.count("tts_lane_ticket_released") == 2
    accepted_acquired = next(
        fields
        for event, fields in logs
        if event == "tts_lane_ticket_acquired" and fields["priority"] == int(TtsLanePriority.ACCEPTED)
    )
    assert accepted_acquired["wait_ms"] >= 0
