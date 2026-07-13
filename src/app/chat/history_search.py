"""Scope-first provider-free retrieval for historical chat messages.

PostgreSQL full-text/search queries are installed for production. Tests use the
in-memory chat repository and deterministic token matching.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.assistant_memory.settings import load_memory_runtime_settings
from app.testing.in_memory_chat_repository import sessions_for_path

from .models import MessageContentPurpose, project_message_content
from .prompt_assembly import PromptHistoryItem
from .repository import default_chat_db_path

_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")


class HistorySearchStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    available: bool
    reason: str
    indexed_messages: int = Field(default=0, ge=0)


class HistorySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PromptHistoryItem] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    status: HistorySearchStatus


def history_recall_enabled() -> bool:
    return load_memory_runtime_settings().history_recall_enabled


class InMemoryHistorySearchService:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_chat_db_path()

    def ensure_index(self) -> HistorySearchStatus:
        count = sum(
            1
            for session in sessions_for_path(self.db_path)
            for message in session.messages
            if message.role in {"user", "assistant"}
            and project_message_content(message, MessageContentPurpose.SEARCH).strip()
        )
        return HistorySearchStatus(
            available=True,
            reason="in_memory_ready",
            indexed_messages=count,
        )

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
        if not terms:
            return HistorySearchResult(items=[], query_terms=terms, status=status)
        matches: list[tuple[int, str, PromptHistoryItem]] = []
        for session in sessions_for_path(self.db_path):
            if session.profile_id != profile_id or session.workspace_id != workspace_id:
                continue
            if (session.project_id or "") != (project_id or ""):
                continue
            if exclude_session_id and session.id == exclude_session_id:
                continue
            for message in session.messages:
                if message.role not in {"user", "assistant"}:
                    continue
                content = project_message_content(message, MessageContentPurpose.SEARCH)
                lowered = content.casefold()
                score = sum(1 for term in terms if term in lowered)
                if score == 0:
                    continue
                matches.append(
                    (
                        -score,
                        message.created_at,
                        PromptHistoryItem(
                            session_id=session.id,
                            message_id=message.id,
                            role=message.role,
                            content=content,
                            created_at=message.created_at,
                        ),
                    )
                )
        matches.sort(key=lambda item: (item[0], item[1], item[2].message_id), reverse=False)
        return HistorySearchResult(
            items=[item[2] for item in matches[: max(0, min(int(limit), 50))]],
            query_terms=terms,
            status=status,
        )


SQLiteHistorySearchService = InMemoryHistorySearchService


def default_history_search_service() -> InMemoryHistorySearchService:
    return InMemoryHistorySearchService()
