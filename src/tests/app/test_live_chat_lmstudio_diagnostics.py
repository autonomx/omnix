from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.gateway import live_chat_lmstudio_diagnostics as diagnostics


def test_channel_error_is_normalized_without_raw_prompt_content() -> None:
    code, summary = diagnostics._classify_lmstudio_error(
        RuntimeError("Unexpected error: Channel Error")
    )

    assert code == "lmstudio_channel_error"
    assert summary == "LM Studio inference channel closed."
    assert "Unexpected" not in summary


def test_nonstream_success_logs_prompt_size_and_provider_metrics(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **fields: events.append((event, fields)),
    )

    provider = SimpleNamespace(config=SimpleNamespace(model="gemma-4-e4b"))
    session = SimpleNamespace(
        messages=[SimpleNamespace(content="old message") for _ in range(93)]
    )
    user_message = SimpleNamespace(content="Hello")

    def original(*args: Any, **kwargs: Any) -> dict[str, Any]:
        active = diagnostics._ACTIVE_CALL.get()
        assert active is not None
        active.update(
            {
                "rendered_message_count": 12,
                "prompt_chars": 4_800,
                "estimated_input_tokens": 1_200,
                "usable_input_tokens": 12_288,
                "truncated_sections": ["recent_messages"],
                "recent_message_count": 10,
            }
        )
        return {
            "content": "Hello back",
            "metadata": {
                "provider_metrics": {
                    "input_tokens": 1_210,
                    "output_tokens": 8,
                    "tokens_per_second": 88.5,
                }
            },
        }

    result = diagnostics._run_lmstudio_nonstream_diagnostics(
        original,
        SimpleNamespace(),
        session,
        user_message,
        provider_id="lmstudio",
        model_id=None,
        context_items=[],
        provider=provider,
    )

    assert result["content"] == "Hello back"
    assert [event for event, _ in events] == [
        "live_chat_lmstudio_nonstream_started",
        "live_chat_lmstudio_nonstream_completed",
    ]
    completed = events[-1][1]
    assert completed["model_id"] == "gemma-4-e4b"
    assert completed["session_message_count"] == 93
    assert completed["rendered_message_count"] == 12
    assert completed["estimated_input_tokens"] == 1_200
    assert completed["input_tokens"] == 1_210
    assert completed["response_chars"] == 10


def test_nonstream_failure_logs_normalized_channel_error(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **fields: events.append((event, fields)),
    )

    provider = SimpleNamespace(config=SimpleNamespace(model="qwen3.5-0.8b"))

    def original(*args: Any, **kwargs: Any) -> dict[str, Any]:
        active = diagnostics._ACTIVE_CALL.get()
        assert active is not None
        active.update(
            {
                "rendered_message_count": 93,
                "prompt_chars": 22_000,
                "estimated_input_tokens": 5_500,
                "usable_input_tokens": 61_440,
                "truncated_sections": [],
                "recent_message_count": 91,
            }
        )
        raise RuntimeError("Unexpected error: Channel Error")

    with pytest.raises(RuntimeError, match="Channel Error"):
        diagnostics._run_lmstudio_nonstream_diagnostics(
            original,
            SimpleNamespace(),
            SimpleNamespace(messages=[object()] * 93),
            SimpleNamespace(content="Hello"),
            provider_id="lmstudio",
            model_id=None,
            context_items=[],
            provider=provider,
        )

    assert [event for event, _ in events] == [
        "live_chat_lmstudio_nonstream_started",
        "live_chat_lmstudio_nonstream_failed",
    ]
    failed = events[-1][1]
    assert failed["model_id"] == "qwen3.5-0.8b"
    assert failed["session_message_count"] == 93
    assert failed["estimated_input_tokens"] == 5_500
    assert failed["error_code"] == "lmstudio_channel_error"
    assert failed["error_summary"] == "LM Studio inference channel closed."
    assert "Channel Error" not in failed["error_summary"]
