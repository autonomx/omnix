from __future__ import annotations

from types import SimpleNamespace

from app.chat.live_call_greeting import stream_live_call_greeting_chunks
from app.chat.models import ChatMessage, ChatSession


def _session() -> ChatSession:
    return ChatSession(
        id="chat:greeting",
        title="Maya call",
        interaction_mode="character",
        character_id="maya",
        active_segment_id="segment:1",
        character_profile_version=1,
        effective_identity_hash="a" * 64,
        message_count=2,
        messages=[
            ChatMessage(
                id="msg:canned",
                role="assistant",
                content="Hey, good to hear from you.",
                created_at="2026-01-01T00:00:00+00:00",
                metadata={"source": "character_profile_greeting"},
            ),
            ChatMessage(
                id="msg:user",
                role="user",
                content="We were talking about hiking.",
                created_at="2026-01-01T00:01:00+00:00",
            ),
        ],
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:01:00+00:00",
    )


def test_generated_greeting_is_ephemeral_and_excludes_canned_profile_line(monkeypatch) -> None:
    session = _session()
    captured: dict[str, object] = {}

    class FakeStore:
        def _provider_messages(self, prompt_session, synthetic_message, context_items):
            captured["prompt_session"] = prompt_session
            captured["synthetic_message"] = synthetic_message
            captured["context_items"] = context_items
            return [
                SimpleNamespace(role="system", content="You are Maya. Be warm and easygoing."),
                SimpleNamespace(role="user", content=synthetic_message.content),
            ]

    class FakeProvider:
        def chat_completion(self, *, messages, model, stream):
            captured["provider_messages"] = messages
            captured["model"] = model
            captured["stream"] = stream
            yield SimpleNamespace(content="Hey there! ", model="test-model", usage={"completion_tokens": 3})
            yield SimpleNamespace(content="How are you doing?", model="test-model")

    monkeypatch.setattr("app.chat.live_call_greeting.shared.get_provider", lambda _name=None: FakeProvider())

    events = list(stream_live_call_greeting_chunks(FakeStore(), session))

    assert events[0] == {"type": "text_chunk", "text": "Hey there!"}
    assert events[1]["type"] == "complete"
    assert events[1]["content"] == "Hey there!"
    assert events[1]["metadata"]["purpose"] == "live_call_greeting"
    assert events[1]["metadata"]["transient"] is True

    prompt_session = captured["prompt_session"]
    assert [message.id for message in prompt_session.messages] == ["msg:user"]
    assert [message.id for message in session.messages] == ["msg:canned", "msg:user"]
    synthetic_message = captured["synthetic_message"]
    assert synthetic_message.metadata == {"source": "live_call_greeting", "transient": True}
    assert captured["context_items"] == []
    assert captured["stream"] is True


def test_generated_greeting_is_bounded_to_one_short_spoken_line(monkeypatch) -> None:
    session = _session()

    class FakeStore:
        def _provider_messages(self, prompt_session, synthetic_message, context_items):
            return [SimpleNamespace(role="user", content=synthetic_message.content)]

    class FakeProvider:
        def chat_completion(self, *, messages, model, stream):
            yield SimpleNamespace(
                content=(
                    "Welcome back to our wonderfully detailed and exceptionally elaborate conversation "
                    "where I might otherwise continue speaking for far too long without stopping"
                ),
                model="test-model",
            )

    monkeypatch.setattr("app.chat.live_call_greeting.shared.get_provider", lambda _name=None: FakeProvider())

    events = list(stream_live_call_greeting_chunks(FakeStore(), session))
    greeting = events[0]["text"]

    assert len(greeting.split()) <= 28
    assert len(greeting) <= 240
    assert greeting.endswith(".")
