from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.chat import prompt_store
from app.gateway import memory_job_offload
from app.chat.models import CreateChatSessionRequest, SendChatMessageRequest


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
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: _StaticProvider())
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("PostgreSQL operation failed")

    monkeypatch.setattr(prompt_store, "enqueue_memory_suggestion_job", unavailable)
    monkeypatch.setattr(memory_job_offload, "enqueue_memory_suggestion_job", unavailable)
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
    assert "memory suggestion maintenance unavailable" in caplog.text
    assert "history compaction maintenance unavailable" in caplog.text
