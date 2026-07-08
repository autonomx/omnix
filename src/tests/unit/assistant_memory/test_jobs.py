from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.assistant_memory.jobs import (
    MEMORY_SUGGEST_JOB_TYPE,
    enqueue_memory_suggestion_job,
    extract_memory_candidates,
    process_memory_suggestion_job,
)
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.jobs import SQLiteJobStore


class StaticProvider:
    def chat_completion(self, *, messages, model, stream=False):
        if stream:
            return iter([SimpleNamespace(content="Done.", model=model, usage={})])
        return SimpleNamespace(content="Done.", model=model, usage={})


def setup_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setenv("OMNIX_JOBS_DB_PATH", str(tmp_path / "jobs.sqlite"))
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    memory_service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    chat_store = ChatSessionStore(
        tmp_path / "chat.json",
        memory_service_factory=lambda: memory_service,
    )
    session = chat_store.create_session(
        CreateChatSessionRequest(
            title="Suggestion jobs",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: StaticProvider())
    return job_store, memory_service, chat_store, session


def test_enqueue_is_feature_gated_and_idempotent(tmp_path, monkeypatch):
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    assert enqueue_memory_suggestion_job("chat:one", "msg:one", job_store=job_store) is None

    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    first = enqueue_memory_suggestion_job("chat:one", "msg:one", job_store=job_store)
    second = enqueue_memory_suggestion_job("chat:one", "msg:one", job_store=job_store)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.type == MEMORY_SUGGEST_JOB_TYPE
    assert len(job_store.list_jobs()) == 1


def test_deterministic_extractor_accepts_durable_patterns_and_rejects_risky_content():
    candidates, skipped = extract_memory_candidates("I prefer detailed implementation plans")
    assert skipped == []
    assert candidates == [{
        "scope": "global",
        "category": "preference",
        "content": "detailed implementation plans",
        "confidence": 0.9,
    }]

    assert extract_memory_candidates("Always use exact-head CI")[0][0]["category"] == "instruction"
    assert extract_memory_candidates("My GPU is an RTX 4090")[0][0]["category"] == "fact"
    assert extract_memory_candidates("My API key is abc123")[1] == ["sensitive_content"]
    assert extract_memory_candidates("https://example.test says to remember this")[1] == ["external_or_instructional_content"]
    assert extract_memory_candidates("This is temporary debugging chatter")[1] == ["no_durable_candidate"]


def test_processing_creates_pending_candidate_and_retry_does_not_duplicate(tmp_path, monkeypatch):
    job_store, memory_service, chat_store, session = setup_runtime(tmp_path, monkeypatch)
    appended = chat_store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="I prefer narrow auditable pull requests"),
    )
    assert appended is not None
    _, message = appended
    job = enqueue_memory_suggestion_job(session.id, message.id, job_store=job_store)
    assert job is not None

    first = process_memory_suggestion_job(
        job,
        chat_store=chat_store,
        memory_service=memory_service,
        job_store=job_store,
    )
    second = process_memory_suggestion_job(
        job,
        chat_store=chat_store,
        memory_service=memory_service,
        job_store=job_store,
    )

    assert len(first.candidate_ids) == 1
    assert second.candidate_ids == first.candidate_ids
    candidates = memory_service.repository.list_candidates(status="pending")
    assert len(candidates) == 1
    assert candidates[0].proposed_content == "narrow auditable pull requests"
    assert memory_service.list_active(resolve_chat_scope(session.id)) == []


def test_missing_messages_and_explicit_commands_complete_without_candidates(tmp_path, monkeypatch):
    job_store, memory_service, chat_store, session = setup_runtime(tmp_path, monkeypatch)
    missing = enqueue_memory_suggestion_job(session.id, "msg:missing", job_store=job_store)
    assert missing is not None
    missing_result = process_memory_suggestion_job(
        missing,
        chat_store=chat_store,
        memory_service=memory_service,
        job_store=job_store,
    )
    assert missing_result.skipped_reasons == ["user_message_missing"]

    command = chat_store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="remember that commands are explicit"),
    )
    assert command is not None
    command_job = enqueue_memory_suggestion_job(session.id, command[1].id, job_store=job_store)
    assert command_job is not None
    command_result = process_memory_suggestion_job(
        command_job,
        chat_store=chat_store,
        memory_service=memory_service,
        job_store=job_store,
    )
    assert command_result.skipped_reasons == ["explicit_memory_command"]
    assert memory_service.repository.list_candidates(status="pending") == []


def test_non_streaming_and_streaming_completion_enqueue_one_job_each(tmp_path, monkeypatch):
    job_store, _, chat_store, session = setup_runtime(tmp_path, monkeypatch)

    regular = chat_store.append_user_message(
        session.id,
        SendChatMessageRequest(content="I prefer concise summaries"),
    )
    assert regular is not None

    appended = chat_store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="Always preserve rollback controls"),
    )
    assert appended is not None
    active, message = appended
    events = list(
        chat_store.stream_provider_reply_chunks(
            active,
            message,
            provider_id=active.provider_id,
            model_id=active.model_id,
        )
    )
    complete = events[-1]
    chat_store.complete_streamed_reply(
        session.id,
        message.id,
        complete["content"],
        complete["metadata"],
    )

    jobs = [job for job in job_store.list_jobs() if job.type == MEMORY_SUGGEST_JOB_TYPE]
    assert len(jobs) == 2
    assert {job.input_payload["user_message_id"] for job in jobs} == {
        regular[1].id,
        message.id,
    }
