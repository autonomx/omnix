from __future__ import annotations

from app.providers import service as provider_service
from app.chat import ChatMessage, ChatSession, ChatSessionStore
from app.chat.compaction import (
    DEFAULT_RECENT_MESSAGE_LIMIT,
    HISTORY_COMPACT_JOB_TYPE,
    InMemoryConversationSummaryRepository,
    build_deterministic_summary,
    enqueue_compaction_job,
    process_compaction_job,
)
from tests.support.in_memory_jobs import InMemoryJobStore

NOW = "2026-07-08T00:00:00+00:00"


def long_session(session_id: str = "chat:long", count: int = 80) -> ChatSession:
    messages = [
        ChatMessage(
            id=f"msg:{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=(
                f"Always preserve decision {index} and next pending task {index}."
                if index % 10 == 0
                else f"Conversation detail {index}."
            ),
            created_at=NOW,
        )
        for index in range(count)
    ]
    return ChatSession(
        id=session_id,
        title="Long conversation",
        created_at=NOW,
        updated_at=NOW,
        message_count=len(messages),
        messages=messages,
    )


def test_deterministic_summary_preserves_recent_boundary_and_key_items():
    session = long_session(count=80)

    first = build_deterministic_summary(session)
    second = build_deterministic_summary(session)

    assert first is not None
    assert second is not None
    assert first.through_message_id == f"msg:{80 - DEFAULT_RECENT_MESSAGE_LIMIT - 1}"
    assert first.source_message_count == 80 - DEFAULT_RECENT_MESSAGE_LIMIT
    assert first.summary == second.summary
    assert first.durable_decisions
    assert first.unresolved_items
    assert "Always preserve decision 0" in first.summary
    assert "Conversation detail 79" not in first.summary


def test_in_memory_summary_repository_is_idempotent_and_versions_new_boundaries(tmp_path):
    repository = InMemoryConversationSummaryRepository(tmp_path / "summaries")
    first = build_deterministic_summary(long_session(count=50))
    assert first is not None
    stored_first = repository.save(first)
    repeated = repository.save(first)
    second = build_deterministic_summary(long_session(count=60))
    assert second is not None
    stored_second = repository.save(second)

    assert stored_first.id == repeated.id
    assert stored_first.revision == 1
    assert stored_second.revision == 2
    assert repository.latest("chat:long").id == stored_second.id


def test_compaction_jobs_are_feature_gated_idempotent_and_durable(tmp_path, monkeypatch):
    session = long_session(count=60)
    job_store = InMemoryJobStore(tmp_path / "jobs")

    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    assert enqueue_compaction_job(session, job_store=job_store) is None

    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_THRESHOLD", "40")
    first = enqueue_compaction_job(session, job_store=job_store)
    second = enqueue_compaction_job(session, job_store=job_store)

    assert first is not None
    assert first.id == second.id
    assert first.type == HISTORY_COMPACT_JOB_TYPE
    assert len(job_store.list_jobs()) == 1


def test_processing_compaction_job_persists_summary_and_completes_job(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_THRESHOLD", "40")
    session = long_session(count=60)
    store = ChatSessionStore(tmp_path / "chat.json")
    store._save_sessions([session])
    job_store = InMemoryJobStore(tmp_path / "jobs")
    summary_repository = InMemoryConversationSummaryRepository(tmp_path / "summaries")
    job = enqueue_compaction_job(session, job_store=job_store)
    assert job is not None

    summary = process_compaction_job(
        job,
        chat_store=store,
        summary_repository=summary_repository,
        job_store=job_store,
    )

    assert summary is not None
    assert summary_repository.latest(session.id).id == summary.id
    completed = next(item for item in job_store.list_jobs() if item.id == job.id)
    assert completed.status == "completed"
    assert completed.output_refs == [{"type": "conversation_summary", "id": summary.id}]


def test_prompt_uses_verified_summary_and_recent_turns_only(monkeypatch, tmp_path):
    session = long_session(count=100)
    summary_repository = InMemoryConversationSummaryRepository(tmp_path / "summaries")
    summary = build_deterministic_summary(session)
    assert summary is not None
    summary_repository.save(summary)
    store = ChatSessionStore(
        tmp_path / "chat.json",
        summary_repository_factory=lambda: summary_repository,
    )
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="Continue",
        created_at=NOW,
    )

    assembly, rendered = store.build_provider_prompt(session, current, [])
    rendered_text = "\n".join(message.content for message in rendered.messages)

    assert assembly.session_summary == summary.summary
    assert len(assembly.recent_messages) == DEFAULT_RECENT_MESSAGE_LIMIT
    assert assembly.recent_messages[0].message_id == f"msg:{100 - DEFAULT_RECENT_MESSAGE_LIMIT}"
    assert "Session summary:" in rendered_text
    assert "Conversation detail 99" in rendered_text
    assert assembly.diagnostics["compaction"]["summary_id"] == summary.id


def test_compaction_enabled_without_persisted_summary_builds_bounded_ephemeral_summary(monkeypatch, tmp_path):
    from app.gateway.live_chat_prompt_window import install_live_chat_prompt_window_hook

    install_live_chat_prompt_window_hook()
    session = long_session(count=50)
    summary_repository = InMemoryConversationSummaryRepository(tmp_path / "summaries")
    store = ChatSessionStore(
        tmp_path / "chat.json",
        summary_repository_factory=lambda: summary_repository,
    )
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setattr(provider_service, "get_global_system_prompt", lambda: "System prompt")
    current = ChatMessage(id="msg:current", role="user", content="Continue", created_at=NOW)

    assembly, _ = store.build_provider_prompt(session, current, [])

    assert assembly.session_summary is not None
    assert "Always preserve decision 0" in assembly.session_summary
    assert "Conversation detail 49" not in assembly.session_summary
    assert len(assembly.recent_messages) == DEFAULT_RECENT_MESSAGE_LIMIT
    assert assembly.diagnostics["compaction"] == {"enabled": True, "summary_id": None}
