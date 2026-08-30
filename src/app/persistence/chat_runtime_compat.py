"""PostgreSQL-backed chat runtime services."""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.assistant_memory import MemoryService, default_memory_service
from app.chat.character_store import _CharacterSessionMixin
from app.chat.compaction import ConversationSummary
from app.chat.history_search import HistorySearchResult, HistorySearchStatus
from app.chat.prompt_assembly import PromptHistoryItem
from app.chat.prompt_store import ChatSessionStore as _PromptChatSessionStore

from .chat_compat import PostgresChatRepositoryAdapter
from .database import PostgresDatabase, default_database
from .document_store import PostgresDocumentStore
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready

_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")


class PostgresConversationSummaryRepository:
    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.documents = PostgresDocumentStore(database)

    def save(self, summary: ConversationSummary) -> ConversationSummary:
        existing = self._by_through(summary.session_id, summary.through_message_id)
        if existing is not None:
            return existing
        latest = self.latest(summary.session_id)
        stored = summary.model_copy(update={"revision": (latest.revision if latest else 0) + 1})
        self.documents.write(
            stored.model_dump(mode="json"),
            module="chat",
            record_type="conversation-summary",
            record_id=stored.id,
        )
        return stored

    def latest(self, session_id: str) -> ConversationSummary | None:
        records = [
            ConversationSummary.model_validate(payload)
            for _, payload, _ in self.documents.list(
                module="chat", record_type="conversation-summary", limit=5000
            )
            if isinstance(payload, dict) and payload.get("session_id") == session_id
        ]
        records.sort(key=lambda item: (item.revision, item.created_at, item.id), reverse=True)
        return records[0] if records else None

    def _by_through(self, session_id: str, through_message_id: str) -> ConversationSummary | None:
        for _, payload, _ in self.documents.list(
            module="chat", record_type="conversation-summary", limit=5000
        ):
            if not isinstance(payload, dict):
                continue
            if payload.get("session_id") == session_id and payload.get("through_message_id") == through_message_id:
                return ConversationSummary.model_validate(payload)
        return None


class PostgresHistorySearchService:
    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def ensure_index(self) -> HistorySearchStatus:
        with self.database.connection() as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_chat_messages WHERE workspace_id = %s",
                    (self.context.workspace_id,),
                ).fetchone()[0]
            )
        return HistorySearchStatus(available=True, reason="postgresql_ready", indexed_messages=count)

    def sync_index(self) -> HistorySearchStatus:
        return self.ensure_index()

    def search(
        self,
        query: str,
        *,
        profile_id: str,
        workspace_id: str,
        project_id: str | None,
        exclude_session_id: str | None = None,
        limit: int = 6,
    ) -> HistorySearchResult:
        terms = list(dict.fromkeys(term.casefold() for term in _TERM_PATTERN.findall(query)))[:12]
        status = self.ensure_index()
        if not terms or workspace_id != self.context.workspace_id:
            return HistorySearchResult(items=[], query_terms=terms, status=status)
        clauses = [
            "message.workspace_id = %s",
            "session.profile_id = %s",
            "COALESCE(session.project_id, '') = %s",
            "message.role IN ('user', 'assistant')",
        ]
        params: list[Any] = [self.context.workspace_id, profile_id, project_id or ""]
        if exclude_session_id:
            clauses.append("message.session_id <> %s")
            params.append(exclude_session_id)
        term_clauses: list[str] = []
        for term in terms:
            term_clauses.append("message.content ILIKE %s")
            params.append(f"%{term}%")
        clauses.append("(" + " OR ".join(term_clauses) + ")")
        params.append(max(0, min(int(limit), 50)))
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT message.id, message.session_id, message.role,
                       message.content, message.created_at
                  FROM omnix_chat_messages AS message
                  JOIN omnix_chat_sessions AS session ON session.id = message.session_id
                 WHERE """
                + " AND ".join(clauses)
                + " ORDER BY message.created_at DESC, message.id ASC LIMIT %s",
                tuple(params),
            ).fetchall()
        return HistorySearchResult(
            items=[
                PromptHistoryItem(
                    session_id=str(row[1]),
                    message_id=str(row[0]),
                    role=str(row[2]),
                    content=str(row[3]),
                    created_at=row[4].isoformat(),
                )
                for row in rows
            ],
            query_terms=terms,
            status=status,
        )


class PostgresChatSessionStore(_PromptChatSessionStore):
    """Preserve chat orchestration while making PostgreSQL the transcript authority."""

    def __init__(
        self,
        path: Any = None,
        *,
        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
        history_search_factory: Callable[[], PostgresHistorySearchService] = PostgresHistorySearchService,
        summary_repository_factory: Callable[[], PostgresConversationSummaryRepository] = PostgresConversationSummaryRepository,
    ) -> None:
        if path is not None:
            raise RuntimeError("file-backed chat authority is retired; use the legacy importer")
        self.path = None
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
        self.summary_repository_factory = summary_repository_factory
        self._repository = PostgresChatRepositoryAdapter()
        self._initialize_prompt_context_cache()

    def _load_sessions(self):
        return self._repository.load_sessions()

    def _save_sessions(self, sessions):
        self._repository.save_sessions(sessions)

    def update_delivery_metadata(
        self,
        *,
        session_id: str,
        assistant_turn_id: str,
        metadata: dict[str, object],
    ) -> bool:
        return self._repository.update_delivery_metadata(
            session_id=session_id,
            assistant_turn_id=assistant_turn_id,
            metadata=metadata,
        )

    def update_user_message_metadata(
        self,
        *,
        session_id: str,
        message_id: str,
        metadata: dict[str, object],
    ) -> bool:
        return self._repository.update_user_message_metadata(
            session_id=session_id,
            message_id=message_id,
            metadata=metadata,
        )


class PostgresCharacterChatSessionStore(_CharacterSessionMixin, PostgresChatSessionStore):
    pass


@lru_cache(maxsize=1)
def default_history_search_service() -> PostgresHistorySearchService:
    """Reuse readiness-checked history search state across chat turns."""
    return PostgresHistorySearchService()


@lru_cache(maxsize=1)
def default_chat_store() -> PostgresCharacterChatSessionStore:
    """Reuse the authoritative chat store instead of re-running startup checks per request."""
    return PostgresCharacterChatSessionStore(
        history_search_factory=default_history_search_service,
    )


def reset_default_chat_runtime_caches() -> None:
    """Clear process-resident defaults for isolated tests and controlled restarts."""
    default_chat_store.cache_clear()
    default_history_search_service.cache_clear()
