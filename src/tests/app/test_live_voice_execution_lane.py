from __future__ import annotations

import threading
import time

from app.gateway.live_voice_execution_lane import (
    PriorityTtsScheduler,
    TtsLanePriority,
    live_voice_execution_lane_config,
    resolve_live_voice_chat_route,
)


class _BlockingProvider:
    def __init__(self) -> None:
        self.speculative_started = threading.Event()
        self.release_speculative = threading.Event()
        self.calls: list[str] = []

    def generate_audio_stream(self, *, text: str, **_kwargs):
        self.calls.append(text)
        if text == "speculative":
            self.speculative_started.set()
            self.release_speculative.wait(timeout=2)
        yield b"\x01\x00", 24_000, {"text": text}


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


def test_accepted_tts_preempts_active_speculative_stream() -> None:
    scheduler = PriorityTtsScheduler()
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
                kwargs={},
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
                kwargs={},
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
