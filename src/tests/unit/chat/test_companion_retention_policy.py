from __future__ import annotations

from types import SimpleNamespace

from app.assistant_memory.jobs import (
    create_memory_suggestion_job_request,
    process_memory_suggestion_job,
)
from app.chat.compaction import build_deterministic_summary, enqueue_compaction_job
from app.chat.memory_commands import MemoryCommand, execute_memory_command
from app.chat.models import ChatMessage, ChatSession
from app.chat.retention_policy import (
    automatic_memory_derivation_allowed,
    transcript_retention_allowed,
)
from app.jobs import InMemoryJobStore


def _message(index: int, role: str = "user") -> ChatMessage:
    return ChatMessage(
        id=f"msg:{index}",
        role=role,
        content=f"message {index}",
        created_at="2026-07-19T00:00:00+00:00",
    )


def _session(*, transcript_policy: str = "persistent", messages: list[ChatMessage] | None = None) -> ChatSession:
    values = list(messages or [])
    return ChatSession(
        id="chat:retention",
        title="Retention test",
        interaction_mode="system",
        transcript_policy=transcript_policy,
        message_count=len(values),
        messages=values,
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
    )


def test_transcript_retention_toggle_is_independent_from_memory_derivation(monkeypatch) -> None:
    session = _session()
    monkeypatch.setenv("OMNIX_CHAT_TRANSCRIPT_RETENTION_ENABLED", "0")

    assert transcript_retention_allowed(session) is False
    assert automatic_memory_derivation_allowed(session) is True

    private = _session(transcript_policy="private")
    assert transcript_retention_allowed(private) is False
    assert automatic_memory_derivation_allowed(private) is False


def test_private_session_memory_job_completes_without_candidate(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_COMPANION_ROLLOUT_STAGE", "review_required")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    session = _session(transcript_policy="private", messages=[_message(1)])
    store = InMemoryJobStore()
    job = store.create_job(create_memory_suggestion_job_request(session.id, "msg:1"))

    result = process_memory_suggestion_job(
        job,
        chat_store=SimpleNamespace(get_session=lambda _session_id: session),
        job_store=store,
    )

    assert result.candidate_ids == []
    assert result.record_ids == []
    assert result.skipped_reasons == ["private_session"]


def test_compaction_never_runs_without_transcript_retention(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_THRESHOLD", "4")
    monkeypatch.setenv("OMNIX_CHAT_TRANSCRIPT_RETENTION_ENABLED", "0")
    messages = [_message(index, "user" if index % 2 else "assistant") for index in range(30)]
    session = _session(messages=messages)

    assert enqueue_compaction_job(session, job_store=InMemoryJobStore()) is None
    assert build_deterministic_summary(session, recent_message_limit=4) is None


def test_private_explicit_save_is_rejected_before_service_mutation() -> None:
    session = _session(transcript_policy="private")

    class RejectMutationService:
        def create_explicit_memory(self, *_args, **_kwargs):
            raise AssertionError("private command reached durable memory service")

    result = execute_memory_command(
        SimpleNamespace(get_session=lambda _session_id: session),
        RejectMutationService(),
        session.id,
        "msg:private",
        MemoryCommand(kind="save", content="secret preference"),
    )

    assert result.mutated is False
    assert result.command == "save"
    assert "Private Chat" in result.content
