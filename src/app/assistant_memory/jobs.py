"""Durable, idempotent post-turn memory suggestion jobs."""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.chat import ChatSessionStore
from app.jobs import CompleteJobRequest, CreateJobRequest, JobRecord, ResourceClass, SQLiteJobStore, default_job_store

from .scope import resolve_chat_scope
from .service import MemoryService, default_memory_service

MEMORY_SUGGEST_JOB_TYPE = "assistant.memory.suggest"
MEMORY_IMPORT_JOB_TYPE = "assistant.memory.import"
MEMORY_CONSOLIDATE_JOB_TYPE = "assistant.memory.consolidate"
HISTORY_COMPACT_JOB_TYPE = "assistant.history.compact"


class MemorySuggestionJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    user_message_id: str
    idempotency_key: str


class MemorySuggestionJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    skipped_reasons: list[str] = Field(default_factory=list)


def memory_suggestions_enabled() -> bool:
    return (os.environ.get("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def suggestion_idempotency_key(session_id: str, user_message_id: str) -> str:
    return hashlib.sha256(f"{MEMORY_SUGGEST_JOB_TYPE}\n{session_id}\n{user_message_id}".encode("utf-8")).hexdigest()


def create_memory_suggestion_job_request(session_id: str, user_message_id: str) -> CreateJobRequest:
    key = suggestion_idempotency_key(session_id, user_message_id)
    return CreateJobRequest(
        owner_id=session_id,
        module="assistant-memory",
        type=MEMORY_SUGGEST_JOB_TYPE,
        resource_class=ResourceClass.CPU,
        input_payload=MemorySuggestionJobInput(
            session_id=session_id,
            user_message_id=user_message_id,
            idempotency_key=key,
        ).model_dump(mode="json"),
        compat={"contract": "assistant_memory_suggestion_v1", "idempotency_key": key},
    )


def enqueue_memory_suggestion_job(
    session_id: str,
    user_message_id: str,
    *,
    job_store: SQLiteJobStore | None = None,
) -> JobRecord | None:
    if not memory_suggestions_enabled():
        return None
    store = job_store or default_job_store()
    key = suggestion_idempotency_key(session_id, user_message_id)
    for job in store.list_jobs():
        if job.type == MEMORY_SUGGEST_JOB_TYPE and job.compat.get("idempotency_key") == key:
            return job
    return store.create_job(create_memory_suggestion_job_request(session_id, user_message_id))


_PREFERENCE = re.compile(r"^(?:i\s+prefer|my\s+preference\s+is)\s+(.{3,400})$", re.IGNORECASE)
_INSTRUCTION = re.compile(r"^(?:always|please\s+always)\s+(.{3,400})$", re.IGNORECASE)
_FACT = re.compile(r"^(?:my|our)\s+([a-z][a-z0-9 _-]{1,60})\s+is\s+(.{2,300})$", re.IGNORECASE)
_SECRET_TERMS = {"password", "secret", "api key", "token", "private key", "credential"}
_EXTERNAL_MARKERS = {"http://", "https://", "context retrieved for this turn", "ignore previous", "system prompt"}


def extract_memory_candidates(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    text = " ".join(content.strip().split())
    lowered = text.casefold()
    if not text:
        return [], ["empty_message"]
    if any(marker in lowered for marker in _EXTERNAL_MARKERS):
        return [], ["external_or_instructional_content"]
    if any(term in lowered for term in _SECRET_TERMS):
        return [], ["sensitive_content"]
    match = _PREFERENCE.match(text)
    if match:
        return [{"scope": "global", "category": "preference", "content": match.group(1).strip(), "confidence": 0.9}], []
    match = _INSTRUCTION.match(text)
    if match:
        return [{"scope": "workspace", "category": "instruction", "content": match.group(1).strip(), "confidence": 0.85}], []
    match = _FACT.match(text)
    if match:
        return [{"scope": "global", "category": "fact", "content": f"{match.group(1).strip()} is {match.group(2).strip()}", "confidence": 0.8}], []
    return [], ["no_durable_candidate"]


def process_memory_suggestion_job(
    job: JobRecord,
    *,
    chat_store: ChatSessionStore,
    memory_service: MemoryService | None = None,
    job_store: SQLiteJobStore | None = None,
) -> MemorySuggestionJobResult:
    if job.type != MEMORY_SUGGEST_JOB_TYPE:
        raise ValueError(f"unsupported memory job type: {job.type}")
    payload = MemorySuggestionJobInput.model_validate(job.input_payload or {})
    session = chat_store.get_session(payload.session_id)
    if session is None:
        result = MemorySuggestionJobResult(job_id=job.id, skipped_reasons=["session_missing"])
    else:
        message = next((item for item in session.messages if item.id == payload.user_message_id and item.role == "user"), None)
        if message is None:
            result = MemorySuggestionJobResult(job_id=job.id, skipped_reasons=["user_message_missing"])
        elif message.metadata.get("memory_command"):
            result = MemorySuggestionJobResult(job_id=job.id, skipped_reasons=["explicit_memory_command"])
        else:
            service = memory_service or default_memory_service()
            context = resolve_chat_scope(
                session.id,
                profile_id=session.profile_id,
                workspace_id=session.workspace_id,
                project_id=session.project_id,
            )
            extracted, skipped = extract_memory_candidates(message.content)
            candidate_ids: list[str] = []
            for item in extracted:
                candidate = service.propose_memory(
                    context,
                    source_session_id=session.id,
                    source_message_id=message.id,
                    scope=item["scope"],
                    category=item["category"],
                    content=item["content"],
                    confidence=item["confidence"],
                    source="assistant_suggested",
                    extraction_metadata={"job_id": job.id, "extractor": "deterministic_v1"},
                )
                candidate_ids.append(candidate.id)
            result = MemorySuggestionJobResult(job_id=job.id, candidate_ids=candidate_ids, skipped_reasons=skipped)
    target_store = job_store or default_job_store()
    target_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[{"type": "memory_candidate", "id": candidate_id} for candidate_id in result.candidate_ids],
            logs=[{"event": "memory.suggestion.processed", **result.model_dump(mode="json")}],
        ),
    )
    return result
