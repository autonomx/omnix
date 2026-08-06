import json
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSession
from app.gateway import live_chat_speculation as speculation
from app.gateway import live_chat_speculation_handshake as handshake
from app.gateway.live_chat_speculation_inline_stream import (
    register_live_chat_speculation_inline_stream_routes,
)


class _FakeProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.started = threading.Event()

    def chat_completion(self, **_kwargs):
        self.calls += 1
        self.started.set()
        return iter(
            [
                SimpleNamespace(content="Hello ", model="fake", usage=None),
                SimpleNamespace(content="there.", model="fake", usage=None),
            ]
        )


class _FakeStore:
    def __init__(self) -> None:
        self.get_session_calls = 0
        self.session = ChatSession(
            id="session-inline",
            title="Inline",
            provider_id="fake-provider",
            model_id="fake-model",
            created_at="2026-08-05T00:00:00+00:00",
            updated_at="2026-08-05T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        self.get_session_calls += 1
        return self.session if session_id == self.session.id else None

    def build_provider_prompt(self, _session, user_message, _context_items):
        rendered = SimpleNamespace(
            messages=[SimpleNamespace(role="user", content=user_message.content)]
        )
        return SimpleNamespace(sources=[]), rendered


def _event_payloads(body: str) -> list[dict]:
    payloads = []
    for block in body.split("\n\n"):
        line = next(
            (line for line in block.splitlines() if line.startswith("data: ")),
            None,
        )
        if line:
            payloads.append(json.loads(line[6:]))
    return payloads


def _client(store: _FakeStore, provider: _FakeProvider, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: provider,
    )
    app = FastAPI()
    speculation.register_live_chat_speculation_routes(
        app,
        chat_store_factory=lambda: store,
    )
    register_live_chat_speculation_inline_stream_routes(
        app,
        chat_store_factory=lambda: store,
    )
    return TestClient(app)


def test_inline_stream_allocates_and_attaches_before_generation(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)

    streamed = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-inline",
            "source_sequence": 8,
        },
    )

    assert streamed.status_code == 200
    assert streamed.headers["x-omnix-speculation-transport"] == (
        "inline-v2-client-id"
    )
    payloads = _event_payloads(streamed.text)
    assert payloads[0]["type"] == "speculation_started"
    assert payloads[0]["inline_stream"] is True
    assert payloads[0]["client_allocated"] is False
    assert "".join(
        payload.get("text", "")
        for payload in payloads
        if payload.get("type") == "text_chunk"
    ) == "Hello there."
    assert payloads[-1]["type"] == "done"
    assert provider.calls == 1
    assert store.get_session_calls == 1


def test_inline_stream_honors_a_valid_client_generation_id(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)
    generation_id = "spec-client-1234567890abcdef"

    streamed = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-inline",
            "source_sequence": 9,
            "generation_id": generation_id,
        },
    )

    assert streamed.status_code == 200
    assert streamed.headers["x-omnix-speculation-generation-id"] == generation_id
    payloads = _event_payloads(streamed.text)
    assert payloads[0]["generation_id"] == generation_id
    assert payloads[0]["client_allocated"] is True


def test_inline_stream_rejects_an_invalid_client_generation_id(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)

    response = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-inline",
            "source_sequence": 10,
            "generation_id": "../../not-valid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_speculation_generation_id"
    assert provider.calls == 0
