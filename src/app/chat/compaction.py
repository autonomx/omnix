"""Durable, versioned long-conversation compaction."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.jobs import CompleteJobRequest, CreateJobRequest, JobRecord, ResourceClass, SQLiteJobStore, default_job_store

from .repository import default_chat_db_path

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
    return (os.environ.get("OMNIX_CHAT_COMPACTION_ENABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def compaction_threshold() -> int:
    try:
        return max(4, int(os.environ.get("OMNIX_CHAT_COMPACTION_THRESHOLD", DEFAULT_COMPACTION_THRESHOLD)))
    except ValueError:
        return DEFAULT_COMPACTION_THRESHOLD


class SQLiteConversationSummaryRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_chat_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_conversation_summaries (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    through_message_id TEXT NOT NULL,
                    source_message_count INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    durable_decisions_json TEXT NOT NULL,
                    unresolved_items_json TEXT NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, through_message_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_summary_session_revision
                ON chat_conversation_summaries(session_id, revision DESC)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def save(self, summary: ConversationSummary) -> ConversationSummary:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_conversation_summaries(
                    id, session_id, through_message_id, source_message_count, summary,
                    durable_decisions_json, unresolved_items_json, token_estimate,
                    revision, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    summary.id,
                    summary.session_id,
                    summary.through_message_id,
                    summary.source_message_count,
                    summary.summary,
                    json.dumps(summary.durable_decisions, sort_keys=True),
                    json.dumps(summary.unresolved_items, sort_keys=True),
                    summary.token_estimate,
                    summary.revision,
                    summary.created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM chat_conversation_summaries
                WHERE session_id = ? AND through_message_id = ?
                """,
                (summary.session_id, summary.through_message_id),
            ).fetchone()
        return self._row(row)

    def latest(self, session_id: str) -> ConversationSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM chat_conversation_summaries
                WHERE session_id = ? ORDER BY revision DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self._row(row) if row else None

    @staticmethod
    def _row(row: sqlite3.Row) -> ConversationSummary:
        return ConversationSummary(
            id=row["id"],
            session_id=row["session_id"],
            through_message_id=row["through_message_id"],
            source_message_count=int(row["source_message_count"]),
            summary=row["summary"],
            durable_decisions=json.loads(row["durable_decisions_json"] or "[]"),
            unresolved_items=json.loads(row["unresolved_items_json"] or "[]"),
            token_estimate=int(row["token_estimate"]),
            revision=int(row["revision"]),
            created_at=row["created_at"],
        )


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0


def build_deterministic_summary(session, *, recent_message_limit: int = DEFAULT_RECENT_MESSAGE_LIMIT) -> ConversationSummary | None:
    from datetime import datetime, timezone

    messages = [message for message in session.messages if message.role in {"user", "assistant"}]
    if len(messages) <= recent_message_limit:
        return None
    older = messages[:-recent_message_limit]
    lines: list[str] = []
    decisions: list[str] = []
    unresolved: list[str] = []
    for message in older:
        content = " ".join(message.content.strip().split())
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
    previous_revision = 0
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
        revision=previous_revision + 1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def compaction_idempotency_key(session_id: str, through_message_id: str) -> str:
    return hashlib.sha256(f"{HISTORY_COMPACT_JOB_TYPE}\n{session_id}\n{through_message_id}".encode("utf-8")).hexdigest()


def enqueue_compaction_job(session, *, job_store: SQLiteJobStore | None = None) -> JobRecord | None:
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
    summary_repository: SQLiteConversationSummaryRepository | None = None,
    job_store: SQLiteJobStore | None = None,
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
        summary = (summary_repository or SQLiteConversationSummaryRepository()).save(summary)
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
