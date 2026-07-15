from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.chat.live_conversation_proactive import (
    ProactiveDeliveryRequest,
    commit_proactive_delivery,
    stream_proactive_turn_chunks,
)
from app.chat.models import ChatMessage, ChatSession
from app.providers import ChatMessage as ProviderMessage


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, chunks):
        self.chunks = chunks
        self.messages = None

    def chat_completion(self, *, messages, model, stream):
        self.messages = messages
        assert stream is True
        return iter(SimpleNamespace(content=value, model=model, usage=None) for value in self.chunks)


class FakeStore:
    def __init__(self, session: ChatSession):
        self.session = session
        self.provider_session = None
        self.completed = False

    def _provider_messages(self, session, synthetic_message, _context):
        self.provider_session = session
        return [
            ProviderMessage(role=message.role, content=message.content)
            for message in [*session.messages, synthetic_message]
        ]

    def get_session(self, session_id):
        return self.session if session_id == self.session.id else None

    def complete_streamed_reply(self, *_args, **_kwargs):
        self.completed = True
        return self.session


def session() -> ChatSession:
    return ChatSession(
        id="chat-1",
        title="Desktop companion",
        provider_id="llm:fake",
        model_id="llm:fake:fake-model",
        message_count=2,
        messages=[
            ChatMessage(id="user-1", role="user", content="Hello", created_at="2026-07-14T12:00:00Z"),
            ChatMessage(
                id="desktop-old",
                role="assistant",
                content="Old screen comment",
                created_at="2026-07-14T12:00:01Z",
                metadata={"transient": True, "purpose": "desktop_companion"},
            ),
        ],
        created_at="2026-07-14T12:00:00Z",
        updated_at="2026-07-14T12:00:01Z",
    )


def test_desktop_generation_uses_internal_prompt_and_filters_transient_history(monkeypatch):
    provider = FakeProvider(["That inventory grid is packed."])
    monkeypatch.setattr(shared, "get_provider", lambda _name=None: provider)
    store = FakeStore(session())

    events = list(
        stream_proactive_turn_chunks(
            store,
            store.session,
            purpose="desktop_companion",
            initiative_reason="desktop_glance",
            state_summary="Current scene: inventory",
            observation_id="obs-1",
            grounding_ids=["obs-1"],
        )
    )

    assert store.provider_session is not None
    assert [message.content for message in store.provider_session.messages] == ["Hello"]
    assert provider.messages[-1].role == "user"
    assert "untrusted observed content" in provider.messages[-1].content
    assert events[-1]["metadata"]["purpose"] == "desktop_companion"
    assert events[-1]["metadata"]["observation_id"] == "obs-1"
    assert events[-1]["metadata"]["grounding_ids"] == ["obs-1"]


def test_desktop_skip_does_not_emit_text_chunk(monkeypatch):
    provider = FakeProvider(["SKIP"])
    monkeypatch.setattr(shared, "get_provider", lambda _name=None: provider)
    store = FakeStore(session())

    events = list(
        stream_proactive_turn_chunks(
            store,
            store.session,
            purpose="desktop_companion",
            initiative_reason="desktop_glance",
        )
    )

    assert [event["type"] for event in events] == ["initiative", "complete"]
    assert events[-1]["content"] == "SKIP"


def test_desktop_delivery_remains_transient_and_does_not_mutate_chat_history():
    store = FakeStore(session())
    before = store.session.message_count
    response = commit_proactive_delivery(
        store,
        "chat-1",
        ProactiveDeliveryRequest(
            turn_id="desktop:one",
            content="That inventory grid is packed.",
            initiative_reason="desktop_glance",
            purpose="desktop_companion",
            observation_id="obs-1",
            grounding_ids=["obs-1"],
        ),
    )

    assert response is not None
    assert response.persisted is False
    assert response.session.message_count == before
    assert store.completed is False
