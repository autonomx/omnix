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
        self.last_request = None
        self.session = ChatSession(
            id="session-1",
            title="Speculation",
            provider_id="fake-provider",
            model_id="fake-model",
            created_at="2026-08-02T00:00:00+00:00",
            updated_at="2026-08-02T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        return self.session if session_id == self.session.id else None

    def build_provider_prompt(self, _session, user_message, _context_items):
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
        line = next((line for line in block.splitlines() if line.startswith("data: ")), None)
        if line:
            payloads.append(json.loads(line[6:]))
    return payloads


def test_transcript_compatibility_is_strict_about_words() -> None:
    assert speculation.transcripts_are_compatible("Tell me a story", "tell me a story!")
    assert not speculation.transcripts_are_compatible("Tell me a story", "Tell me the story")
    assert not speculation.transcript_is_speculation_safe("Wait, no I mean tell me a story")


def test_generation_has_no_persistence_until_final_accept(monkeypatch) -> None:
    store = _FakeStore()
    monkeypatch.setattr(speculation.shared, "get_provider", lambda _provider_id: _FakeProvider())
    app = FastAPI()
    speculation.register_live_chat_speculation_routes(app, chat_store_factory=lambda: store)
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
    generation_id = next(
        payload["generation_id"]
        for payload in payloads
        if payload.get("type") == "speculation_started"
    )
    assert "".join(
        payload.get("text", "") for payload in payloads if payload.get("type") == "text_chunk"
    ) == "Hello there."
    assert store.begin_calls == 0
    assert store.complete_calls == 0

    mismatch = client.post(
        f"/api/live/speculation/sessions/session-1/{generation_id}/accept",
        json={"final_text": "Tell me the story"},
    )
    assert mismatch.status_code == 409
    assert store.begin_calls == 0

    accepted = client.post(
        f"/api/live/speculation/sessions/session-1/{generation_id}/accept",
        json={
            "final_text": "tell me a story!",
            "user_turn_id": "user-turn:accepted-17",
            "speech_segment_id": "speech-segment:accepted-17",
            "live_voice_turn_id": "voice-turn:accepted-17",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["content"] == "Hello there."
    assert accepted.json()["user_turn_id"] == "user-turn:accepted-17"
    assert accepted.json()["speech_segment_id"] == "speech-segment:accepted-17"
    assert store.begin_calls == 1
    assert store.complete_calls == 1
    assert store.last_request is not None
    assert store.last_request.user_turn_id == "user-turn:accepted-17"
    assert store.last_request.speech_segment_id == "speech-segment:accepted-17"
    assert re.fullmatch(r"spec-[0-9a-f]{32}", generation_id)
