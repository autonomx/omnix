"""Versioned long-conversation compaction.

PostgreSQL is installed for production. Provider-free tests use the in-memory
summary repository defined here; no SQLite schema remains.
"""
from __future__ import annotations

import hashlib
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.assistant_memory.settings import load_memory_runtime_settings
from app.jobs import CompleteJobRequest, CreateJobRequest, JobRecord, ResourceClass, default_job_store

from .models import MessageContentPurpose, project_message_content

if TYPE_CHECKING:
    from .prompt_store import ChatSessionStore

HISTORY_COMPACT_JOB_TYPE = "assistant.history.compact"
DEFAULT_RECENT_MESSAGE_LIMIT = 24
DEFAULT_COMPACTION_THRESHOLD = 40


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    through_message_id: str
    source_message_count: int = Field(ge=1)
    summary: str
    durable_decisions: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    token_estimate: int = Field(ge=0)
    revision: int = Field(ge=1)
    created_at: str


class CompactionJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    through_message_id: str
    idempotency_key: str
    recent_message_limit: int = Field(default=DEFAULT_RECENT_MESSAGE_LIMIT, ge=2, le=200)


def compaction_enabled() -> bool:
    return load_memory_runtime_settings().compaction_enabled


def compaction_threshold() -> int:
    try:
        return max(4, int(os.environ.get("OMNIX_CHAT_COMPACTION_THRESHOLD", DEFAULT_COMPACTION_THRESHOLD)))
    except ValueError:
        return DEFAULT_COMPACTION_THRESHOLD


_SUMMARIES: dict[str, dict[str, ConversationSummary]] = {}
_SUMMARY_LOCK = threading.RLock()


class InMemoryConversationSummaryRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else Path(":memory:")
        self._key = str(self.db_path)

    def save(self, summary: ConversationSummary) -> ConversationSummary:
        with _SUMMARY_LOCK:
            records = _SUMMARIES.setdefault(self._key, {})
            for existing in records.values():
                if (
                    existing.session_id == summary.session_id
                    and existing.through_message_id == summary.through_message_id
                ):
                    return deepcopy(existing)
            latest = max(
                (
                    item.revision
                    for item in records.values()
                    if item.session_id == summary.session_id
                ),
                default=0,
            )
            stored = summary.model_copy(update={"revision": latest + 1})
            records[stored.id] = deepcopy(stored)
            return deepcopy(stored)

    def latest(self, session_id: str) -> ConversationSummary | None:
        with _SUMMARY_LOCK:
            values = [
                item
                for item in _SUMMARIES.setdefault(self._key, {}).values()
                if item.session_id == session_id
            ]
            values.sort(key=lambda item: (item.revision, item.created_at, item.id), reverse=True)
            return deepcopy(values[0]) if values else None


SQLiteConversationSummaryRepository = InMemoryConversationSummaryRepository


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0


def build_deterministic_summary(session: Any, *, recent_message_limit: int = DEFAULT_RECENT_MESSAGE_LIMIT) -> ConversationSummary | None:
    from datetime import datetime, timezone

    messages = [message for message in session.messages if message.role in {"user", "assistant"}]
    if len(messages) <= recent_message_limit:
        return None
    older = messages[:-recent_message_limit]
    lines: list[str] = []
    decisions: list[str] = []
    unresolved: list[str] = []
    for message in older:
        projected = project_message_content(message, MessageContentPurpose.SUMMARY)
        content = " ".join(projected.strip().split())
        if not content:
            continue
        clipped = content[:500] + ("…" if len(content) > 500 else "")
        lines.append(f"{message.role}: {clipped}")
        lowered = content.casefold()
        if message.role == "user" and any(marker in lowered for marker in ("use ", "always ", "decision", "source of truth")):
            decisions.append(clipped)
        if "todo" in lowered or "next" in lowered or "pending" in lowered or content.endswith("?"):
            unresolved.append(clipped)
    text = "\n".join(lines)
    if len(text) > 12_000:
        text = text[-12_000:]
    through = older[-1]
    summary_id = hashlib.sha256(f"{session.id}\n{through.id}".encode("utf-8")).hexdigest()
    return ConversationSummary(
        id=f"summary:{summary_id}",
        session_id=session.id,
        through_message_id=through.id,
        source_message_count=len(older),
        summary=text,
        durable_decisions=list(dict.fromkeys(decisions))[:20],
        unresolved_items=list(dict.fromkeys(unresolved))[:20],
        token_estimate=_estimate_tokens(text),
        revision=1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def compaction_idempotency_key(session_id: str, through_message_id: str) -> str:
    return hashlib.sha256(f"{HISTORY_COMPACT_JOB_TYPE}\n{session_id}\n{through_message_id}".encode("utf-8")).hexdigest()


def enqueue_compaction_job(session: Any, *, job_store: Any | None = None) -> JobRecord | None:
    if not compaction_enabled() or len(session.messages) < compaction_threshold():
        return None
    messages = [message for message in session.messages if message.role in {"user", "assistant"}]
    if len(messages) <= DEFAULT_RECENT_MESSAGE_LIMIT:
        return None
    through = messages[-DEFAULT_RECENT_MESSAGE_LIMIT - 1]
    key = compaction_idempotency_key(session.id, through.id)
    store = job_store or default_job_store()
    for job in store.list_jobs():
        if job.type == HISTORY_COMPACT_JOB_TYPE and job.compat.get("idempotency_key") == key:
            return job
    return store.create_job(
        CreateJobRequest(
            owner_id=session.id,
            module="assistant-memory",
            type=HISTORY_COMPACT_JOB_TYPE,
            resource_class=ResourceClass.CPU,
            input_payload=CompactionJobInput(
                session_id=session.id,
                through_message_id=through.id,
                idempotency_key=key,
            ).model_dump(mode="json"),
            compat={"contract": "assistant_history_compaction_v1", "idempotency_key": key},
        )
    )


def process_compaction_job(
    job: JobRecord,
    *,
    chat_store: "ChatSessionStore",
    summary_repository: Any | None = None,
    job_store: Any | None = None,
) -> ConversationSummary | None:
    if job.type != HISTORY_COMPACT_JOB_TYPE:
        raise ValueError(f"unsupported compaction job type: {job.type}")
    payload = CompactionJobInput.model_validate(job.input_payload or {})
    session = chat_store.get_session(payload.session_id)
    summary = None if session is None else build_deterministic_summary(
        session,
        recent_message_limit=payload.recent_message_limit,
    )
    if summary is not None and summary.through_message_id == payload.through_message_id:
        summary = (summary_repository or InMemoryConversationSummaryRepository()).save(summary)
    (job_store or default_job_store()).complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=(
                [{"type": "conversation_summary", "id": summary.id}]
                if summary is not None else []
            ),
            logs=[{
                "event": "history.compaction.processed",
                "summary_id": summary.id if summary else None,
            }],
        ),
    )
    return summary
