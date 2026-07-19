"""Durable, idempotent post-turn structured memory jobs."""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs import (
    CompleteJobRequest,
    CreateJobRequest,
    InMemoryJobStore,
    JobRecord,
    ResourceClass,
    default_job_store,
)

from .models import MemoryCandidate, MemoryRecord
from .owner_defaults import default_memory_service
from .rollout import companion_rollout_policy
from .scope import resolve_session_memory_scope
from .settings import load_memory_runtime_settings
from .structured_consolidation import consolidate_structured_proposal
from .structured_extraction import extract_structured_memory_proposals
from .service import MemoryService

if TYPE_CHECKING:
    from app.chat import ChatSessionStore

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
    record_ids: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    skipped_reasons: list[str] = Field(default_factory=list)


def memory_suggestions_enabled() -> bool:
    settings = load_memory_runtime_settings()
    policy = companion_rollout_policy(settings)
    return settings.suggestions_enabled and (
        policy.review_candidates_enabled
        or policy.automatic_direct_assertions_enabled
    )


def suggestion_idempotency_key(session_id: str, user_message_id: str) -> str:
    return hashlib.sha256(
        f"{MEMORY_SUGGEST_JOB_TYPE}\n{session_id}\n{user_message_id}".encode("utf-8")
    ).hexdigest()


def create_memory_suggestion_job_request(
    session_id: str,
    user_message_id: str,
) -> CreateJobRequest:
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
        compat={"contract": "assistant_memory_suggestion_v2", "idempotency_key": key},
    )


def enqueue_memory_suggestion_job(
    session_id: str,
    user_message_id: str,
    *,
    job_store: InMemoryJobStore | None = None,
) -> JobRecord | None:
    if not memory_suggestions_enabled():
        return None
    store = job_store or default_job_store()
    key = suggestion_idempotency_key(session_id, user_message_id)
    for job in store.list_jobs():
        if job.type == MEMORY_SUGGEST_JOB_TYPE and job.compat.get("idempotency_key") == key:
            return job
    return store.create_job(create_memory_suggestion_job_request(session_id, user_message_id))


def extract_memory_candidates(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Compatibility adapter exposing the structured extractor as dictionaries."""

    proposals, skipped = extract_structured_memory_proposals(
        content,
        source_message_id="compat:message",
    )
    return [proposal.model_dump(mode="json") for proposal in proposals], skipped


def _complete_result(
    result: MemorySuggestionJobResult,
    *,
    store: InMemoryJobStore,
) -> None:
    output_refs = [
        {"type": "memory_candidate", "id": candidate_id}
        for candidate_id in result.candidate_ids
    ] + [
        {"type": "memory_record", "id": record_id}
        for record_id in result.record_ids
    ]
    store.complete_job(
        result.job_id,
        CompleteJobRequest(
            output_refs=output_refs,
            logs=[
                {
                    "event": "memory.suggestion.processed",
                    "job_id": result.job_id,
                    "candidate_count": len(result.candidate_ids),
                    "record_count": len(result.record_ids),
                    "actions": result.actions,
                    "skipped_reasons": result.skipped_reasons,
                }
            ],
        ),
    )


def process_memory_suggestion_job(
    job: JobRecord,
    *,
    chat_store: ChatSessionStore,
    memory_service: MemoryService | None = None,
    job_store: InMemoryJobStore | None = None,
) -> MemorySuggestionJobResult:
    if job.type != MEMORY_SUGGEST_JOB_TYPE:
        raise ValueError(f"unsupported memory job type: {job.type}")
    payload = MemorySuggestionJobInput.model_validate(job.input_payload or {})
    session = chat_store.get_session(payload.session_id)
    result = MemorySuggestionJobResult(job_id=job.id)
    settings = load_memory_runtime_settings()
    rollout = companion_rollout_policy(settings)
    if not rollout.review_candidates_enabled and not rollout.automatic_direct_assertions_enabled:
        result.skipped_reasons.append("rollout_stage_disabled")
    elif session is None:
        result.skipped_reasons.append("session_missing")
    elif session.interaction_mode == "character" and not session.write_memory:
        result.skipped_reasons.append("character_memory_write_disabled")
    else:
        message = next(
            (
                item
                for item in session.messages
                if item.id == payload.user_message_id and item.role == "user"
            ),
            None,
        )
        if message is None:
            result.skipped_reasons.append("user_message_missing")
        elif message.metadata.get("memory_command"):
            result.skipped_reasons.append("explicit_memory_command")
        else:
            service = memory_service or default_memory_service()
            context = resolve_session_memory_scope(session)
            proposals, skipped = extract_structured_memory_proposals(
                message.content,
                source_message_id=message.id,
            )
            result.skipped_reasons.extend(skipped)
            for proposal in proposals:
                action, entity = consolidate_structured_proposal(
                    service,
                    context,
                    proposal,
                    source_session_id=session.id,
                    source_message_id=message.id,
                    auto_save_direct_assertions=(
                        rollout.automatic_direct_assertions_enabled
                    ),
                )
                result.actions.append(action)
                if isinstance(entity, MemoryCandidate):
                    result.candidate_ids.append(entity.id)
                elif isinstance(entity, MemoryRecord):
                    result.record_ids.append(entity.id)

    _complete_result(result, store=job_store or default_job_store())
    return result


__all__ = [
    "HISTORY_COMPACT_JOB_TYPE",
    "MEMORY_CONSOLIDATE_JOB_TYPE",
    "MEMORY_IMPORT_JOB_TYPE",
    "MEMORY_SUGGEST_JOB_TYPE",
    "MemorySuggestionJobInput",
    "MemorySuggestionJobResult",
    "create_memory_suggestion_job_request",
    "enqueue_memory_suggestion_job",
    "extract_memory_candidates",
    "memory_suggestions_enabled",
    "process_memory_suggestion_job",
]
