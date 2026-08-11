from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.gateway.live_chat_stream_retry import (
    EmptyProviderStreamError,
    retry_provider_stream,
)
from app.providers.base import ConnectionError as ProviderConnectionError
from app.providers.exceptions import RateLimitError


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


def test_rate_limit_cause_is_not_retried_or_sent_to_fallback() -> None:
    calls = 0
    fallback_calls = 0
    sleeps: list[float] = []

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        try:
            raise RateLimitError("provider rate limit exceeded")
        except RateLimitError as exc:
            raise ProviderConnectionError("Failed to start provider stream") from exc
        yield  # pragma: no cover

    def fallback_factory() -> dict[str, object]:
        nonlocal fallback_calls
        fallback_calls += 1
        return {"content": "should never run", "metadata": {}}

    with pytest.raises(RateLimitError, match="provider rate limit exceeded"):
        list(
            retry_provider_stream(
                stream_factory,
                fallback_factory,
                attempts=4,
                retry_base_delay_ms=250,
                retry_max_delay_ms=1000,
                fallback_delay_ms=1000,
                sleep_fn=sleeps.append,
            )
        )

    assert calls == 1
    assert fallback_calls == 0
    assert sleeps == []


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


def test_fourth_attempt_recovers_after_transient_burst() -> None:
    calls = 0
    sleeps: list[float] = []

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls < 4:
            raise RuntimeError("provider is temporarily unavailable")
        yield {"type": "text_chunk", "text": "Recovered after cooldown."}
        yield {
            "type": "complete",
            "content": "Recovered after cooldown.",
            "metadata": {"generation_status": "completed"},
        }

    def fallback_factory() -> dict[str, object]:
        raise AssertionError("fallback should not run after fourth-attempt recovery")

    events = list(
        retry_provider_stream(
            stream_factory,
            fallback_factory,
            attempts=4,
            retry_base_delay_ms=50,
            retry_max_delay_ms=200,
            sleep_fn=sleeps.append,
        )
    )

    assert calls == 4
    assert sleeps == pytest.approx([0.05, 0.1, 0.2])
    assert events[0] == {"type": "text_chunk", "text": "Recovered after cooldown."}


def test_applies_bounded_backoff_and_fallback_cooldown() -> None:
    calls = 0
    sleeps: list[float] = []

    def stream_factory() -> Iterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        raise RuntimeError("stream unavailable")
        yield  # pragma: no cover

    def fallback_factory() -> dict[str, object]:
        return {"content": "Fallback response.", "metadata": {}}

    events = list(
        retry_provider_stream(
            stream_factory,
            fallback_factory,
            attempts=3,
            retry_base_delay_ms=100,
            retry_max_delay_ms=150,
            fallback_delay_ms=250,
            sleep_fn=sleeps.append,
        )
    )

    assert calls == 3
    assert sleeps == pytest.approx([0.1, 0.15, 0.25])
    assert events[-1]["type"] == "complete"


def test_raises_last_error_when_stream_and_fallback_are_empty() -> None:
    def stream_factory() -> Iterator[dict[str, object]]:
        yield {"type": "complete", "content": "", "metadata": {}}

    def fallback_factory() -> dict[str, object]:
        return {"content": "", "metadata": {}}

    with pytest.raises(EmptyProviderStreamError, match="fallback completed without assistant text"):
        list(retry_provider_stream(stream_factory, fallback_factory, attempts=2))
