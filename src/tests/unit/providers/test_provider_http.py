"""Providers on pooled HTTP clients (WP-7.2)."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app.providers import (
    AuthenticationError,
    CerebrasProvider,
    ChatMessage,
    LMStudioProvider,
    OpenRouterProvider,
    ProviderConfig,
)
from app.providers.exceptions import RateLimitError
from app.runtime.cancellation import CancellationToken
from tests.support.http import install_provider_http, mock_http_client

MESSAGES = [ChatMessage(role="user", content="Hi")]


class _GatedStream(httpx.SyncByteStream):
    """SSE body that sends one chunk, waits for ``gate``, then finishes."""

    def __init__(self, gate: threading.Event, started: threading.Event, word: str) -> None:
        self.gate, self.started, self.word = gate, started, word
        self.closed = threading.Event()

    def __iter__(self):
        yield f'data: {{"choices":[{{"delta":{{"content":"{self.word}"}}}}]}}\n\n'.encode()
        self.started.set()
        self.gate.wait(5)
        if self.closed.is_set():
            return
        yield b"data: [DONE]\n\n"

    def close(self) -> None:
        self.closed.set()
        self.gate.set()


def test_two_providers_stream_at_once_and_neither_is_closed_mid_stream() -> None:
    gate = threading.Event()
    started = {"openrouter": threading.Event(), "cerebras": threading.Event()}
    streams = {}

    def serve(name: str, word: str):
        def handle(request: httpx.Request) -> httpx.Response:
            streams[name] = _GatedStream(gate, started[name], word)
            return httpx.Response(200, stream=streams[name])

        return handle

    openrouter = OpenRouterProvider(ProviderConfig(provider_type="openrouter", api_key="k", model="m"))
    cerebras = CerebrasProvider(ProviderConfig(provider_type="cerebras", api_key="k", model="m"))
    install_provider_http(openrouter, serve("openrouter", "first"))
    install_provider_http(cerebras, serve("cerebras", "second"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: [c.content for c in openrouter.chat_completion(MESSAGES, stream=True)])
        second = pool.submit(lambda: [c.content for c in cerebras.chat_completion(MESSAGES, stream=True)])
        assert all(event.wait(2) for event in started.values())  # both mid-stream together
        assert not any(stream.closed.is_set() for stream in streams.values())
        gate.set()
        assert first.result(timeout=2) == ["first"]
        assert second.result(timeout=2) == ["second"]


@pytest.mark.parametrize(("status", "error"), [(401, AuthenticationError), (429, RateLimitError)])
def test_error_statuses_map_to_provider_errors(status, error) -> None:
    provider = OpenRouterProvider(ProviderConfig(provider_type="openrouter", api_key="k", model="m"))
    install_provider_http(provider, lambda request: httpx.Response(status, json={"error": "no"}))

    with pytest.raises(error):
        provider.chat_completion(MESSAGES)


def test_a_503_from_the_provider_is_retried() -> None:
    replies = iter([httpx.Response(503), httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})])
    provider = OpenRouterProvider(ProviderConfig(provider_type="openrouter", api_key="k", model="m"))
    provider.__dict__["_http_client"] = mock_http_client(lambda request: next(replies), retries=1)

    assert provider.chat_completion(MESSAGES).content == "ok"


def test_cancelling_an_lmstudio_stream_ends_it_within_200_ms() -> None:
    gate, started = threading.Event(), threading.Event()
    body = _GatedStream(gate, started, "partial")
    provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", model="m"))
    install_provider_http(provider, lambda request: httpx.Response(200, stream=body))
    token = CancellationToken()

    with ThreadPoolExecutor(max_workers=1) as pool:
        chunks = pool.submit(lambda: [c.content for c in provider.chat_completion(MESSAGES, stream=True, cancel=token)])
        assert started.wait(2)
        cancelled_at = time.perf_counter()
        token.cancel()
        result = chunks.result(timeout=1)
        elapsed = time.perf_counter() - cancelled_at

    assert result == ["partial"]
    assert body.closed.is_set()
    assert elapsed < 0.2
