import json
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSession
from app.gateway import live_chat_speculation as speculation
from app.gateway import live_chat_speculation_handshake as handshake
from app.gateway import live_chat_speculation_inline_stream as inline_stream
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
    monkeypatch.setattr(
        inline_stream,
        "resolve_effective_provider_id",
        lambda _provider_id: "fake-provider",
    )
    monkeypatch.setattr(
        inline_stream,
        "live_call_provider_affinity",
        lambda _session_id: None,
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


def test_local_vite_origin_can_preflight_direct_gateway_speculation() -> None:
    app = FastAPI(title="Omnix Web Gateway")
    response = TestClient(app).options(
        "/api/live/speculation/sessions/session-inline/start-stream",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_nonlocal_origin_is_not_allowed_by_direct_gateway_cors() -> None:
    app = FastAPI(title="Omnix Web Gateway")
    response = TestClient(app).options(
        "/api/live/speculation/sessions/session-inline/start-stream",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


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
    assert streamed.headers["x-omnix-live-execution-lane"] == "session"
    payloads = _event_payloads(streamed.text)
    assert payloads[0]["type"] == "speculation_started"
    assert payloads[0]["inline_stream"] is True
    assert payloads[0]["client_allocated"] is False
    assert payloads[0]["execution_lane"] == "session"
    assert "".join(
        payload.get("text", "")
        for payload in payloads
        if payload.get("type") == "text_chunk"
    ) == "Hello there."
    assert payloads[-1]["type"] == "done"
    assert provider.calls == 1
    assert store.get_session_calls == 1


def test_inline_stream_suppresses_cerebras_before_provider_generation(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    store.session.provider_id = "cerebras"
    store.session.model_id = None
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)
    monkeypatch.setattr(
        inline_stream,
        "resolve_effective_provider_id",
        lambda _provider_id: "cerebras",
    )

    response = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-cerebras",
            "source_sequence": 9,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "speculation_provider_suppressed"
    assert provider.calls == 0
    assert handshake._HANDSHAKE_GENERATIONS == {}


def test_inline_stream_ignores_stale_session_provider_after_settings_switch(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    store.session.provider_id = "cerebras"
    store.session.model_id = "old-cerebras-model"
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)
    monkeypatch.setattr(
        inline_stream,
        "resolve_effective_provider_id",
        lambda _provider_id: "lmstudio",
    )
    monkeypatch.setattr(
        inline_stream,
        "live_call_provider_affinity",
        lambda _session_id: ("lmstudio", None),
    )

    response = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-settings-switch",
            "source_sequence": 10,
        },
    )

    assert response.status_code == 200
    assert response.headers["x-omnix-speculation-provider-id"] == "lmstudio"
    assert response.headers.get("x-omnix-speculation-model-id") is None
    payloads = _event_payloads(response.text)
    assert payloads[0]["provider_id"] == "lmstudio"
    assert payloads[0]["model_id"] is None
    assert provider.calls == 1


def test_inline_stream_uses_dedicated_live_model_lane(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_PROVIDER_ID", "fast-provider")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "fast-live-model")
    store = _FakeStore()
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)

    streamed = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-inline",
            "source_sequence": 11,
        },
    )

    assert streamed.status_code == 200
    assert streamed.headers["x-omnix-live-execution-lane"] == "dedicated"
    assert streamed.headers["x-omnix-speculation-provider-id"] == "fast-provider"
    assert streamed.headers["x-omnix-speculation-model-id"] == "fast-live-model"
    payloads = _event_payloads(streamed.text)
    assert payloads[0]["execution_lane"] == "dedicated"
    assert payloads[0]["provider_id"] == "fast-provider"
    assert payloads[0]["model_id"] == "fast-live-model"


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


def test_inline_stream_supersedes_older_hypothesis_for_same_utterance(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    client = _client(store, provider, monkeypatch)
    old_id = "spec-client-oldhypothesis123"
    old_pending = speculation._Speculation(
        generation_id=old_id,
        session_id=store.session.id,
        candidate_text="Tell me a",
        provider_id="fake-provider",
        model_id="fake-model",
        segment_id="segment-supersede",
        source_sequence=12,
        created_at=speculation.time.time(),
        execution_lane="session",
    )
    old_generation = handshake._HandshakeGeneration(
        store=store,
        session=store.session,
    )
    with speculation._SPECULATION_LOCK:
        speculation._SPECULATIONS[old_id] = old_pending
        handshake._HANDSHAKE_GENERATIONS[old_id] = old_generation

    streamed = client.post(
        "/api/live/speculation/sessions/session-inline/start-stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-supersede",
            "source_sequence": 12,
            "generation_id": "spec-client-newhypothesis456",
        },
    )

    assert streamed.status_code == 200
    assert old_generation.cancel_event.is_set()
    assert old_pending.completed is True
    assert old_pending.error == "speculation_superseded"


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
