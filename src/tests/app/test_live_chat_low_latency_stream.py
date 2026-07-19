from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app import shared
from app.gateway.live_chat_low_latency_stream import (
    LowLatencyTextChunker,
    _stream_low_latency_reply,
)
from app.providers import ChatResponse


def test_low_latency_chunker_keeps_split_words_intact() -> None:
    chunker = LowLatencyTextChunker()

    assert chunker.push("How") == []
    assert chunker.push("dy ") == ["Howdy "]
    assert chunker.push("right back") == []
    assert chunker.push(" at ya.") == ["right back at ya."]
    assert chunker.flush() == ""


def test_generic_provider_emits_first_word_before_sentence_and_retains_usage(monkeypatch) -> None:
    class FakeProvider:
        provider_name = "cerebras"

        def chat_completion(self, **kwargs: Any):
            assert kwargs["stream"] is True
            return iter(
                [
                    ChatResponse(content="How", model="fast-model"),
                    ChatResponse(content="dy ", model="fast-model"),
                    ChatResponse(content="right", model="fast-model"),
                    ChatResponse(content=" back", model="fast-model"),
                    ChatResponse(content=" at ya.", model="fast-model"),
                    ChatResponse(
                        content="",
                        model="fast-model",
                        usage={"completion_tokens": 6},
                        finish_reason="stop",
                    ),
                ]
            )

    monkeypatch.setattr(shared, "get_provider", lambda name: FakeProvider())
    rendered = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="Hello")],
    )
    store = SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (
            SimpleNamespace(diagnostics={}),
            rendered,
        ),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )

    events = list(
        _stream_low_latency_reply(
            store,
            SimpleNamespace(id="chat:test"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="llm:cerebras",
            model_id="llm:cerebras:fast-model",
            context_items=[],
        )
    )

    text_events = [event["text"] for event in events if event["type"] == "text_chunk"]
    assert text_events[0] == "Howdy "
    assert "".join(text_events) == "Howdy right back at ya."
    assert events[-1]["type"] == "complete"
    assert events[-1]["content"] == "Howdy right back at ya."
    assert events[-1]["metadata"]["usage"] == {"completion_tokens": 6}
