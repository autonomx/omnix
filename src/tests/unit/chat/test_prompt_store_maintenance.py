from __future__ import annotations

from types import SimpleNamespace

from app.providers import service as provider_service
from app.platform.chat import prompt_store
from app.platform.chat.models import CreateChatSessionRequest, SendChatMessageRequest


class _StaticProvider:
    def chat_completion(self, *, messages, model, stream=False):
        del messages, stream
        return SimpleNamespace(content="Completed response.", model=model, usage={})


def test_character_memory_suggestions_require_write_permission():
    assert prompt_store._memory_suggestions_allowed(
        SimpleNamespace(interaction_mode="character", write_memory=False)
    ) is False
    assert prompt_store._memory_suggestions_allowed(
        SimpleNamespace(interaction_mode="character", write_memory=True)
    ) is True
    assert prompt_store._memory_suggestions_allowed(
        SimpleNamespace(interaction_mode="system", write_memory=False)
    ) is True


def test_post_turn_maintenance_failure_does_not_fail_completed_chat(
    tmp_path,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(provider_service, "get_provider", lambda provider_name=None: _StaticProvider())
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("PostgreSQL operation failed")

    monkeypatch.setattr(prompt_store.ChatSessionStore, "_publish_turn_completed", unavailable)
    monkeypatch.setattr(prompt_store, "enqueue_compaction_job", unavailable)
    store = prompt_store.ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="Maintenance outage",
            interaction_mode="system",
            provider_id="lmstudio",
        )
    )

    appended = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="This turn must still succeed"),
    )

    assert appended is not None
    persisted = store.get_session(session.id)
    assert persisted is not None
    assert persisted.messages[-1].role == "assistant"
    assert persisted.messages[-1].metadata["generation_status"] == "completed"
    assert "turn completed event unavailable" in caplog.text
    assert "history compaction maintenance unavailable" in caplog.text


def test_a_completed_turn_publishes_its_event_once_with_the_memory_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(provider_service, "get_provider", lambda provider_name=None: _StaticProvider())
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")
    published = []
    monkeypatch.setattr(
        prompt_store.ChatSessionStore, "_publish_turn_completed",
        lambda _store, session, user_message_id: published.append(
            prompt_store.turn_completed_event(session, user_message_id, user_id="user:1")
        ),
    )
    store = prompt_store.ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Events", interaction_mode="system", provider_id="lmstudio"))

    store.append_user_message(session.id, SendChatMessageRequest(content="Hello"))

    (event,) = published
    user_message = next(message for message in store.get_session(session.id).messages if message.role == "user")
    assert (event.session_id, event.user_message_id, event.memory_writes_allowed) == (session.id, user_message.id, True)
