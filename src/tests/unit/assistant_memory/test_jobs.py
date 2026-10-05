from __future__ import annotations

from types import SimpleNamespace

from app.providers import service as provider_service
from app.assistant_memory import MemoryService, InMemoryMemoryRepository, resolve_chat_scope
from app.assistant_memory.jobs import (
    MEMORY_SUGGEST_JOB_TYPE,
    enqueue_memory_suggestion_job,
    extract_memory_candidates,
    process_memory_suggestion_job,
)
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from tests.support.in_memory_jobs import InMemoryJobStore
import pytest

pytestmark = pytest.mark.usefixtures("legacy_test_persistence")


class StaticProvider:
    def chat_completion(self, *, messages, model, stream=False):
        if stream:
            return iter([SimpleNamespace(content="Done.", model=model, usage={})])
        return SimpleNamespace(content="Done.", model=model, usage={})


def setup_runtime(tmp_path, monkeypatch):
    from app.assistant_memory import jobs as memory_jobs

    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    job_store = InMemoryJobStore(tmp_path / "jobs")
    monkeypatch.setattr(memory_jobs, "default_job_store", lambda: job_store)
    memory_service = MemoryService(InMemoryMemoryRepository(tmp_path / "memory.sqlite3"))
    chat_store = ChatSessionStore(
        tmp_path / "chat.json",
        memory_service_factory=lambda: memory_service,
        job_service=job_store,
    )
    session = chat_store.create_session(
        CreateChatSessionRequest(
            title="Suggestion jobs",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )
    monkeypatch.setattr(provider_service, "get_provider", lambda provider_name=None: StaticProvider())
    return job_store, memory_service, chat_store, session


def test_enqueue_is_feature_gated_and_idempotent(tmp_path, monkeypatch):
    job_store = InMemoryJobStore(tmp_path / "jobs")
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
    assert len(candidates) == 1
    assert candidates[0]["kind"] == "preference"
    assert candidates[0]["category"] == "preference"
    assert candidates[0]["content"] == "The user prefers detailed implementation plans"
    assert candidates[0]["confidence"] == 0.95

    instruction = extract_memory_candidates("Always use exact-head CI")[0][0]
    assert instruction["kind"] == "instruction"
    assert instruction["category"] == "instruction"
    assert instruction["content"] == "use exact-head CI"
    gpu_fact = extract_memory_candidates("My GPU is an RTX 4090")[0][0]
    assert gpu_fact["kind"] == "semantic_fact"
    assert gpu_fact["category"] == "fact"
    assert gpu_fact["content"] == "The user's GPU is an RTX 4090"
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
    assert candidates[0].proposed_content == "The user prefers narrow auditable pull requests"
    assert memory_service.list_active(resolve_chat_scope(session.id)) == []


