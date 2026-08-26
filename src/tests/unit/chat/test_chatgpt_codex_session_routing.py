"""Chat-store routing regressions for the ChatGPT Codex provider."""
from __future__ import annotations

from types import SimpleNamespace

from app.chat.models import ChatMessage, ChatSession
from app.chat.store import ChatSessionStore


class _FakeCodexProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(
                [
                    SimpleNamespace(content="Hello from Plus.", model="gpt-5.6-sol", usage=None),
                    SimpleNamespace(
                        content="",
                        model="gpt-5.6-sol",
                        usage={"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
                    ),
                ]
            )
        return SimpleNamespace(
            content="Hello from Plus.",
            model="gpt-5.6-sol",
            usage={"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
            thinking=None,
            reasoning=None,
        )


def _session() -> tuple[ChatSession, ChatMessage]:
    session = ChatSession(
        id="chat:exact-session-id",
        title="Codex chat",
        provider_id="chatgpt_codex",
        model_id=None,
        message_count=1,
        messages=[
            ChatMessage(
                id="msg:system",
                role="system",
                content="Be concise.",
                created_at="2026-08-24T20:00:00-07:00",
            )
        ],
        created_at="2026-08-24T20:00:00-07:00",
        updated_at="2026-08-24T20:00:00-07:00",
    )
    user_message = ChatMessage(
        id="msg:user",
        role="user",
        content="Hello",
        created_at="2026-08-24T20:01:00-07:00",
    )
    return session, user_message


def test_non_streaming_codex_call_uses_exact_omnix_session_id(monkeypatch, tmp_path):
    from app import shared

    provider = _FakeCodexProvider()
    monkeypatch.setattr(shared, "get_provider", lambda _name=None: provider)
    session, user_message = _session()
    store = ChatSessionStore(tmp_path / "chat.json")

    result = store._generate_provider_reply(
        session,
        user_message,
        provider_id="chatgpt_codex",
        model_id=None,
        context_items=[],
    )

    assert result["content"] == "Hello from Plus."
    assert provider.calls[0]["conversation_id"] == session.id
    assert provider.calls[0]["stream"] is False


def test_streaming_codex_call_uses_session_id_and_preserves_final_usage(monkeypatch, tmp_path):
    from app import shared

    provider = _FakeCodexProvider()
    monkeypatch.setattr(shared, "get_provider", lambda _name=None: provider)
    session, user_message = _session()
    store = ChatSessionStore(tmp_path / "chat.json")

    events = list(
        store.stream_provider_reply_chunks(
            session,
            user_message,
            provider_id="chatgpt_codex",
            model_id=None,
            context_items=[],
        )
    )

    assert provider.calls[0]["conversation_id"] == session.id
    assert provider.calls[0]["stream"] is True
    complete = events[-1]
    assert complete["type"] == "complete"
    assert complete["content"] == "Hello from Plus."
    assert complete["metadata"]["usage"] == {
        "prompt_tokens": 9,
        "completion_tokens": 3,
        "total_tokens": 12,
    }


def test_non_codex_provider_does_not_receive_codex_specific_conversation_kwarg(monkeypatch, tmp_path):
    from app import shared

    provider = _FakeCodexProvider()
    monkeypatch.setattr(shared, "get_provider", lambda _name=None: provider)
    session, user_message = _session()
    store = ChatSessionStore(tmp_path / "chat.json")

    store._generate_provider_reply(
        session,
        user_message,
        provider_id="lmstudio",
        model_id="local-model",
        context_items=[],
    )

    assert "conversation_id" not in provider.calls[0]
