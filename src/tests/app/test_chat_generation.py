from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def chat_completion(self, *, messages, model, stream=False):
        self.calls.append({"messages": messages, "model": model, "stream": stream})
        return SimpleNamespace(
            content="Hello from the provider.",
            model=model or "default-model",
            usage={"total_tokens": 12},
            thinking="",
            reasoning="",
        )


def test_chat_store_invokes_provider_and_persists_assistant_message(monkeypatch, tmp_path):
    provider = FakeProvider()
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="New chat",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )

    updated, user_message = store.append_user_message(
        session.id,
        SendChatMessageRequest(
            content="hey",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        ),
    )

    assert user_message.role == "user"
    assert [message.role for message in updated.messages] == ["user", "assistant"]
    assert updated.messages[-1].content == "Hello from the provider."
    assert updated.messages[-1].metadata["generation_status"] == "completed"
    assert updated.messages[-1].metadata["resolved_model"] == "test-model"
    assert updated.message_count == 2

    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == "test-model"
    prompt_messages = provider.calls[0]["messages"]
    assert [message.role for message in prompt_messages] == ["system", "user"]
    assert prompt_messages[0].content == "System prompt"
    assert prompt_messages[1].content == "hey"

    reloaded = store.get_session(session.id)
    assert reloaded is not None
    assert reloaded.messages[-1].role == "assistant"
    assert reloaded.messages[-1].content == "Hello from the provider."
