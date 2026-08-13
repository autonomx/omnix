from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

from app.gateway import live_chat_speculation as speculation_runtime
from app.providers import ChatMessage as ProviderMessage
from app.providers import ChatResponse, LMStudioProvider, ProviderConfig


class _BlockingStreamResponse:
    def __init__(self) -> None:
        self.iter_started = threading.Event()
        self.closed = threading.Event()
        self.close_calls = 0

    def iter_lines(self):
        self.iter_started.set()
        self.closed.wait(timeout=2.0)
        if self.closed.is_set():
            raise OSError("stream closed")
        yield b"data: [DONE]"

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()


class _CapturingProvider:
    provider_name = "lmstudio"

    def __init__(self) -> None:
        self.cancel_event: threading.Event | None = None

    def chat_completion(self, **kwargs: Any):
        self.cancel_event = kwargs.get("_cancel_event")
        return iter([ChatResponse(content="Ready.", model="fake")])


class _FakeStore:
    def build_provider_prompt(self, _session, user_message, _context_items):
        rendered = SimpleNamespace(
            messages=[SimpleNamespace(role="user", content=user_message.content)]
        )
        return SimpleNamespace(sources=[]), rendered


def test_lmstudio_stream_cancel_closes_blocked_response_before_ttft(monkeypatch) -> None:
    provider = LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model="test-model",
        )
    )
    response = _BlockingStreamResponse()
    captured_payloads: list[dict[str, Any]] = []

    def fake_request(payload, *, stream, include_metrics, timeout=None):
        captured_payloads.append(dict(payload))
        assert stream is True
        assert include_metrics is False
        return response

    monkeypatch.setattr(provider, "_make_chat_completion_request", fake_request)
    cancel_event = threading.Event()
    stream = provider.chat_completion(
        messages=[ProviderMessage(role="user", content="Hello")],
        model="test-model",
        stream=True,
        _cancel_event=cancel_event,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(list, stream)
        assert response.iter_started.wait(timeout=1.0)

        started = time.perf_counter()
        cancel_event.set()
        result = future.result(timeout=0.5)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert result == []
    assert response.closed.is_set()
    assert response.close_calls >= 1
    assert elapsed_ms < 500.0
    assert len(captured_payloads) == 1
    assert "_cancel_event" not in captured_payloads[0]


def test_side_effect_free_lmstudio_speculation_receives_cancel_event(monkeypatch) -> None:
    provider = _CapturingProvider()
    monkeypatch.setattr(
        speculation_runtime.shared,
        "get_provider",
        lambda _provider_id: provider,
    )
    pending = speculation_runtime._Speculation(
        generation_id="spec-cancel-forwarding",
        session_id="session-cancel-forwarding",
        candidate_text="Tell me something",
        provider_id="lmstudio",
        model_id="test-model",
        segment_id="segment-cancel-forwarding",
        source_sequence=1,
        created_at=time.time(),
    )
    cancel_event = threading.Event()

    events = list(
        speculation_runtime._generate_side_effect_free(
            _FakeStore(),
            SimpleNamespace(),
            pending,
            cancel_event=cancel_event,
        )
    )

    assert provider.cancel_event is cancel_event
    assert pending.completed is True
    assert any('"type": "text_chunk"' in event for event in events)
