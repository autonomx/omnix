from __future__ import annotations

import json
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


def _store() -> SimpleNamespace:
    rendered = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="Hello")],
    )
    return SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (
            SimpleNamespace(diagnostics={}),
            rendered,
        ),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )


def test_typed_chat_emits_its_first_provider_fragment_and_retains_usage(monkeypatch) -> None:
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

    events = list(
        _stream_low_latency_reply(
            _store(),
            SimpleNamespace(id="chat:test"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="llm:cerebras",
            model_id="llm:cerebras:fast-model",
            context_items=[],
        )
    )

    text_events = [event["text"] for event in events if event["type"] == "text_chunk"]
    assert text_events[0] == "How"
    assert "".join(text_events) == "Howdy right back at ya."
    assert events[-1]["type"] == "complete"
    assert events[-1]["content"] == "Howdy right back at ya."
    assert events[-1]["metadata"]["usage"] == {"completion_tokens": 6}
    json.dumps(events[-1])


def test_codex_low_latency_path_reuses_exact_omnix_session(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeProvider:
        provider_name = "chatgpt_codex"

        def chat_completion(self, **kwargs: Any):
            calls.append(kwargs)
            return iter([ChatResponse(content="Hello from Plus.", model="gpt-5.6-sol")])

    monkeypatch.setattr(shared, "get_provider", lambda name: FakeProvider())

    events = list(
        _stream_low_latency_reply(
            _store(),
            SimpleNamespace(id="chat:exact-low-latency-session"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="chatgpt_codex",
            model_id="gpt-5.6-sol",
            context_items=[],
        )
    )

    assert events[-1]["content"] == "Hello from Plus."
    assert calls[0]["stream"] is True
    assert calls[0]["conversation_id"] == "chat:exact-low-latency-session"


def test_non_codex_low_latency_path_does_not_receive_conversation_id(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeProvider:
        provider_name = "cerebras"

        def chat_completion(self, **kwargs: Any):
            calls.append(kwargs)
            return iter([ChatResponse(content="Hello.", model="fast-model")])

    monkeypatch.setattr(shared, "get_provider", lambda name: FakeProvider())

    list(
        _stream_low_latency_reply(
            _store(),
            SimpleNamespace(id="chat:ordinary-provider"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="cerebras",
            model_id="fast-model",
            context_items=[],
        )
    )

    assert "conversation_id" not in calls[0]


def test_provider_usage_model_is_normalized_before_terminal_sse_serialization(monkeypatch) -> None:
    class UsageModel:
        def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
            assert mode == "json"
            return {
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "details": {"cached": False},
            }

    class FakeProvider:
        provider_name = "lmstudio"

        def chat_completion(self, **kwargs: Any):
            assert kwargs["stream"] is True
            return iter(
                [
                    SimpleNamespace(content="Hello ", model="local-model", usage=None),
                    SimpleNamespace(content="there.", model="local-model", usage=None),
                    SimpleNamespace(content="", model="local-model", usage=UsageModel()),
                ]
            )

    monkeypatch.setattr(shared, "get_provider", lambda name: FakeProvider())

    events = list(
        _stream_low_latency_reply(
            _store(),
            SimpleNamespace(id="chat:test"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="lmstudio",
            model_id="local-model",
            context_items=[],
        )
    )

    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["metadata"]["usage"] == {
        "prompt_tokens": 4,
        "completion_tokens": 2,
        "details": {"cached": False},
    }
    json.dumps(terminal)
