from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.gateway.live_chat_stream_retry import (
    EmptyProviderStreamError,
    retry_provider_stream,
)


def test_retries_failure_before_first_text() -> None:
    calls = 0

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary provider failure")
        yield {"type": "text_chunk", "text": "Recovered response."}
        yield {
            "type": "complete",
            "content": "Recovered response.",
            "metadata": {"generation_status": "completed"},
        }

    events = list(retry_provider_stream(stream_factory, None, attempts=3))

    assert calls == 2
    assert [event["type"] for event in events] == ["text_chunk", "complete"]
    assert events[0]["text"] == "Recovered response."


def test_retries_empty_completion_before_first_text() -> None:
    calls = 0

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {"type": "complete", "content": "", "metadata": {}}
            return
        yield {"type": "complete", "content": "Completion-only response.", "metadata": {}}

    events = list(retry_provider_stream(stream_factory, None, attempts=3))

    assert calls == 2
    assert events == [
        {"type": "text_chunk", "text": "Completion-only response."},
        {"type": "complete", "content": "Completion-only response.", "metadata": {}},
    ]


def test_does_not_retry_after_partial_text_delivery() -> None:
    calls = 0

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        yield {"type": "text_chunk", "text": "Partial response"}
        raise RuntimeError("provider failed after delivery")

    stream = retry_provider_stream(stream_factory, None, attempts=3)

    assert next(stream) == {"type": "text_chunk", "text": "Partial response"}
    with pytest.raises(RuntimeError, match="provider failed after delivery"):
        next(stream)
    assert calls == 1


def test_uses_non_streaming_fallback_after_stream_attempts_exhausted() -> None:
    calls = 0

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        raise RuntimeError("stream unavailable")
        yield  # pragma: no cover

    def fallback_factory() -> dict[str, object]:
        return {
            "content": "Fallback response.",
            "metadata": {"generation_status": "completed", "delivery": "fallback"},
        }

    events = list(retry_provider_stream(stream_factory, fallback_factory, attempts=3))

    assert calls == 3
    assert events == [
        {"type": "text_chunk", "text": "Fallback response."},
        {
            "type": "complete",
            "content": "Fallback response.",
            "metadata": {"generation_status": "completed", "delivery": "fallback"},
        },
    ]


def test_raises_last_error_when_stream_and_fallback_are_empty() -> None:
    def stream_factory() -> Iterator[dict[str, object]]:
        yield {"type": "complete", "content": "", "metadata": {}}

    def fallback_factory() -> dict[str, object]:
        return {"content": "", "metadata": {}}

    with pytest.raises(EmptyProviderStreamError, match="fallback completed without assistant text"):
        list(retry_provider_stream(stream_factory, fallback_factory, attempts=2))
