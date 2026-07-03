from __future__ import annotations

from app.live_speech.llm import EchoTextGenerator, OpenAICompatibleTextGenerator, create_text_generator_from_env
from app.live_speech.realtime import LiveSpeechRealtimeService


def test_echo_generator_streams_prompt_text() -> None:
    chunks = list(EchoTextGenerator().generate("hello there"))

    assert chunks == ["I heard: hello there"]


def test_openai_compatible_generator_falls_back_when_unavailable() -> None:
    generator = OpenAICompatibleTextGenerator(base_url="http://127.0.0.1:1", timeout_seconds=0.01)

    chunks = list(generator.generate("hello"))

    assert chunks == ["I heard: hello"]


def test_text_generator_factory_selects_real_provider(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SPEECH_LLM_PROVIDER", "real")
    monkeypatch.setenv("LIVE_SPEECH_LLM_BASE_URL", "http://example.test/v1")
    monkeypatch.setenv("LIVE_SPEECH_LLM_MODEL", "model-a")

    generator = create_text_generator_from_env()

    assert isinstance(generator, OpenAICompatibleTextGenerator)
    assert generator.base_url == "http://example.test/v1"
    assert generator.model == "model-a"


def test_realtime_service_uses_injected_text_generator() -> None:
    service = LiveSpeechRealtimeService(text_generator=EchoTextGenerator(prefix="Reply:"))
    service.inject_text("hello")

    events = service.create_response()
    text_events = [evt for evt in events if evt.type == "response.text.delta"]

    assert text_events
    assert text_events[0].payload["delta"] == "Reply: hello"
