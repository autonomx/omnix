import json
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatMessage, ChatSession
from app.gateway import live_chat_speculation as speculation
from app.gateway import live_chat_speculation_handshake as handshake


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


class _BlockingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def chat_completion(self, **_kwargs):
        self.calls += 1
        self.started.set()

        def generate():
            self.release.wait(timeout=2)
            yield SimpleNamespace(content="Too late.", model="fake", usage=None)

        return generate()


class _FakeStore:
    def __init__(self) -> None:
        self.get_session_calls = 0
        self.begin_calls = 0
        self.complete_calls = 0
        self.session = ChatSession(
            id="session-handshake",
            title="Handshake",
            provider_id="fake-provider",
            model_id="fake-model",
            created_at="2026-08-04T00:00:00+00:00",
            updated_at="2026-08-04T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        self.get_session_calls += 1
        return self.session if session_id == self.session.id else None

    def build_provider_prompt(self, _session, user_message, _context_items):
        rendered = SimpleNamespace(
            messages=[SimpleNamespace(role="user", content=user_message.content)]
        )
        return SimpleNamespace(sources=[]), rendered

    def begin_user_message(self, session_id, request):
        assert session_id == self.session.id
        self.begin_calls += 1
        user_message = ChatMessage(
            id="accepted-user",
            role="user",
            content=request.content,
            created_at="2026-08-04T00:00:01+00:00",
        )
        return self.session, user_message

    def complete_streamed_reply(
        self,
        session_id,
        user_message_id,
        content,
        metadata,
    ):
        assert session_id == self.session.id
        assert user_message_id == "accepted-user"
        self.complete_calls += 1
        self.session.messages = [
            ChatMessage(
                id="accepted-user",
                role="user",
                content="Tell me a story",
                created_at="2026-08-04T00:00:01+00:00",
            ),
            ChatMessage(
                id="accepted-assistant",
                role="assistant",
                content=content,
                created_at="2026-08-04T00:00:02+00:00",
                metadata=metadata,
            ),
        ]
        return self.session


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


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _client(store: _FakeStore) -> TestClient:
    app = FastAPI()
    speculation.register_live_chat_speculation_routes(
        app,
        chat_store_factory=lambda: store,
    )
    handshake.register_live_chat_speculation_handshake_routes(
        app,
        chat_store_factory=lambda: store,
    )
    return TestClient(app)


def test_json_handshake_starts_generation_before_stream_attachment(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: provider,
    )
    client = _client(store)

    started = client.post(
        "/api/live/speculation/sessions/session-handshake/start",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-handshake",
            "source_sequence": 2,
        },
    )

    assert started.status_code == 200
    start_payload = started.json()
    generation_id = start_payload["generation_id"]
    assert start_payload["provider_id"] == "fake-provider"
    assert start_payload["model_id"] == "fake-model"
    assert provider.started.wait(timeout=1)
    assert _wait_until(
        lambda: speculation._SPECULATIONS[generation_id].completed,
    )
    assert provider.calls == 1
    assert store.get_session_calls == 1
    assert store.begin_calls == 0
    assert store.complete_calls == 0

    streamed = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/stream"
    )

    assert streamed.status_code == 200
    payloads = _event_payloads(streamed.text)
    assert "".join(
        payload.get("text", "")
        for payload in payloads
        if payload.get("type") == "text_chunk"
    ) == "Hello there."
    assert payloads[-1]["type"] == "done"
    assert store.get_session_calls == 1
    assert store.begin_calls == 0
    assert store.complete_calls == 0

    accepted = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/accept",
        json={
            "final_text": "tell me a story!",
            "user_turn_id": "voice-user-turn:handshake",
            "speech_segment_id": "voice-segment:handshake",
            "live_voice_turn_id": "voice-turn:handshake",
        },
    )

    assert accepted.status_code == 200
    assert accepted.json()["content"] == "Hello there."
    assert store.begin_calls == 1
    assert store.complete_calls == 1


def test_generation_stream_is_single_consumer(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _FakeProvider()
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: provider,
    )
    client = _client(store)

    start_payload = client.post(
        "/api/live/speculation/sessions/session-handshake/start",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-single-consumer",
            "source_sequence": 3,
        },
    ).json()
    generation_id = start_payload["generation_id"]

    first = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/stream"
    )
    second = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/stream"
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "speculation_stream_already_started"


def test_cancel_marks_eager_generation_failed_without_persistence(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    handshake.clear_live_speculation_handshake_state()
    store = _FakeStore()
    provider = _BlockingProvider()
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: provider,
    )
    client = _client(store)

    start_payload = client.post(
        "/api/live/speculation/sessions/session-handshake/start",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-cancel",
            "source_sequence": 4,
        },
    ).json()
    generation_id = start_payload["generation_id"]
    assert provider.started.wait(timeout=1)

    cancelled = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/cancel"
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["already_completed"] is False
    assert speculation._SPECULATIONS[generation_id].completed is True
    assert speculation._SPECULATIONS[generation_id].error == "speculation_cancelled"
    assert store.begin_calls == 0
    assert store.complete_calls == 0

    streamed = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/stream"
    )
    payloads = _event_payloads(streamed.text)
    assert streamed.status_code == 200
    assert payloads[0]["type"] == "error"
    assert payloads[0]["code"] == "speculation_cancelled"
    assert payloads[-1]["type"] == "done"

    accepted = client.post(
        f"/api/live/speculation/sessions/session-handshake/{generation_id}/accept",
        json={"final_text": "Tell me a story"},
    )
    assert accepted.status_code == 409
    assert accepted.json()["detail"] == "speculation_failed"

    provider.release.set()
    handshake.clear_live_speculation_handshake_state()
