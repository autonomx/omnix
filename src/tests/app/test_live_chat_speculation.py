import json
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatMessage, ChatSession
from app.gateway import live_chat_speculation as speculation


class _FakeProvider:
    def chat_completion(self, **_kwargs):
        return iter(
            [
                SimpleNamespace(content="Hello ", model="fake", usage=None),
                SimpleNamespace(content="there.", model="fake", usage=None),
            ]
        )


class _FakeStore:
    def __init__(self) -> None:
        self.begin_calls = 0
        self.complete_calls = 0
        self.get_session_calls = 0
        self.last_request = None
        self.last_metadata = None
        self.last_prompt_metadata = None
        self.session = ChatSession(
            id="session-1",
            title="Speculation",
            provider_id="fake-provider",
            model_id="fake-model",
            created_at="2026-08-02T00:00:00+00:00",
            updated_at="2026-08-02T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        self.get_session_calls += 1
        return self.session if session_id == self.session.id else None

    def build_provider_prompt(self, _session, user_message, _context_items):
        self.last_prompt_metadata = dict(user_message.metadata)
        rendered = SimpleNamespace(
            messages=[SimpleNamespace(role="user", content=user_message.content)]
        )
        return SimpleNamespace(sources=[]), rendered

    def begin_user_message(self, session_id, request):
        assert session_id == self.session.id
        self.begin_calls += 1
        self.last_request = request
        message = ChatMessage(
            id="accepted-user",
            role="user",
            content=request.content,
            created_at="2026-08-02T00:00:01+00:00",
        )
        return self.session, message

    def complete_streamed_reply(self, session_id, user_message_id, content, metadata):
        assert session_id == self.session.id
        assert user_message_id == "accepted-user"
        assert metadata["speculative_generation"] is True
        self.complete_calls += 1
        self.last_metadata = metadata
        self.session.messages = [
            ChatMessage(
                id="accepted-user",
                role="user",
                content="Tell me a story",
                created_at="2026-08-02T00:00:01+00:00",
            ),
            ChatMessage(
                id="accepted-assistant",
                role="assistant",
                content=content,
                created_at="2026-08-02T00:00:02+00:00",
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


def test_transcript_compatibility_is_strict_about_words() -> None:
    assert speculation.transcripts_are_compatible(
        "Tell me a story",
        "tell me a story!",
    )
    assert not speculation.transcripts_are_compatible(
        "Tell me a story",
        "Tell me the story",
    )
    assert speculation.transcript_is_speculation_safe("Hello")
    assert not speculation.transcript_is_speculation_safe("Hi")
    assert not speculation.transcript_is_speculation_safe(
        "Wait, no I mean tell me a story"
    )


def test_generation_has_no_persistence_until_final_accept(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    store = _FakeStore()
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: _FakeProvider(),
    )
    app = FastAPI()
    speculation.register_live_chat_speculation_routes(
        app,
        chat_store_factory=lambda: store,
    )
    client = TestClient(app)

    stream_response = client.post(
        "/api/live/speculation/sessions/session-1/stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-1",
            "source_sequence": 0,
        },
    )
    assert stream_response.status_code == 200
    payloads = _event_payloads(stream_response.text)
    started = next(
        payload for payload in payloads if payload.get("type") == "speculation_started"
    )
    generation_id = started["generation_id"]
    assert stream_response.headers["x-omnix-speculation-generation-id"] == generation_id
    assert stream_response.headers["x-omnix-speculation-provider-id"] == "fake-provider"
    assert stream_response.headers["x-omnix-speculation-model-id"] == "fake-model"
    assert stream_response.headers["x-accel-buffering"] == "no"
    assert "no-store" in stream_response.headers["cache-control"]
    assert len(stream_response.text) >= speculation._SPECULATION_PREAMBLE_CHARS
    assert started["provider_id"] == "fake-provider"
    assert started["model_id"] == "fake-model"
    assert "".join(
        payload.get("text", "")
        for payload in payloads
        if payload.get("type") == "text_chunk"
    ) == "Hello there."
    assert store.last_prompt_metadata["side_effects_allowed"] is False
    assert store.last_prompt_metadata["tools_allowed"] is False
    assert store.last_prompt_metadata["memory_writes_allowed"] is False
    assert store.last_prompt_metadata["user_turn_id"].startswith("voice-user-turn:spec-")
    assert store.last_prompt_metadata["speech_segment_id"] == "voice-segment:segment-1"
    assert store.get_session_calls == 1
    assert store.begin_calls == 0
    assert store.complete_calls == 0

    mismatch = client.post(
        f"/api/live/speculation/sessions/session-1/{generation_id}/accept",
        json={"final_text": "Tell me the story"},
    )
    assert mismatch.status_code == 409
    assert store.begin_calls == 0

    offloaded_functions: list[str] = []
    original_to_thread = speculation.asyncio.to_thread

    async def tracked_to_thread(function, /, *args, **kwargs):
        offloaded_functions.append(getattr(function, "__name__", "unknown"))
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(speculation.asyncio, "to_thread", tracked_to_thread)
    accepted = client.post(
        f"/api/live/speculation/sessions/session-1/{generation_id}/accept",
        json={
            "final_text": "tell me a story!",
            "user_turn_id": "voice-user-turn:test-1",
            "speech_segment_id": "voice-segment:test-1",
            "live_voice_turn_id": "voice-turn:test-1",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["content"] == "Hello there."
    assert store.begin_calls == 1
    assert store.complete_calls == 1
    assert offloaded_functions[-2:] == [
        "begin_user_message",
        "complete_streamed_reply",
    ]
    assert store.last_request.user_turn_id == "voice-user-turn:test-1"
    assert store.last_request.speech_segment_id == "voice-segment:test-1"
    assert store.last_metadata["live_voice_turn_id"] == "voice-turn:test-1"
    assert re.fullmatch(r"spec-[0-9a-f]{32}", generation_id)


def test_primed_session_avoids_speculation_reload(monkeypatch) -> None:
    speculation.clear_live_speculation_session_cache()
    store = _FakeStore()
    speculation.prime_live_speculation_session(store.session)
    monkeypatch.setattr(
        speculation.shared,
        "get_provider",
        lambda _provider_id: _FakeProvider(),
    )
    app = FastAPI()
    speculation.register_live_chat_speculation_routes(
        app,
        chat_store_factory=lambda: store,
    )
    client = TestClient(app)

    response = client.post(
        "/api/live/speculation/sessions/session-1/stream",
        json={
            "content": "Tell me a story",
            "segment_id": "segment-primed",
            "source_sequence": 0,
        },
    )

    assert response.status_code == 200
    assert store.get_session_calls == 0
    assert any(
        payload.get("type") == "text_chunk"
        for payload in _event_payloads(response.text)
    )
