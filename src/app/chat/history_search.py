"""Scope-first FTS5 retrieval for historical Chat messages."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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
    return (os.environ.get("OMNIX_CHAT_HISTORY_RECALL_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class SQLiteHistorySearchService:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_chat_db_path()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def ensure_index(self) -> HistorySearchStatus:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chat_message_fts USING fts5(
                        message_id UNINDEXED,
                        session_id UNINDEXED,
                        profile_id UNINDEXED,
                        workspace_id UNINDEXED,
                        project_id UNINDEXED,
                        role UNINDEXED,
                        content,
                        created_at UNINDEXED
                    )
                    """
                )
                count = int(connection.execute("SELECT COUNT(*) FROM chat_message_fts").fetchone()[0])
            return HistorySearchStatus(available=True, reason="ready", indexed_messages=count)
        except sqlite3.OperationalError as exc:
            return HistorySearchStatus(available=False, reason=f"fts5_unavailable:{exc}")

    def sync_index(self) -> HistorySearchStatus:
        status = self.ensure_index()
        if not status.available:
            return status
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM chat_message_fts")
                connection.execute(
                    """
                    INSERT INTO chat_message_fts(
                        message_id, session_id, profile_id, workspace_id,
                        project_id, role, content, created_at
                    )
                    SELECT
                        message.id,
                        message.session_id,
                        session.profile_id,
                        session.workspace_id,
                        COALESCE(session.project_id, ''),
                        message.role,
                        message.content,
                        message.created_at
                    FROM chat_messages AS message
                    JOIN chat_sessions AS session ON session.id = message.session_id
                    WHERE message.role IN ('user', 'assistant')
                    """
                )
                count = int(connection.execute("SELECT COUNT(*) FROM chat_message_fts").fetchone()[0])
            return HistorySearchStatus(available=True, reason="ready", indexed_messages=count)
        except sqlite3.OperationalError as exc:
            return HistorySearchStatus(available=False, reason=f"fts5_sync_failed:{exc}")

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
        status = self.sync_index()
        terms = list(dict.fromkeys(term.casefold() for term in _TERM_PATTERN.findall(query)))[:12]
        if not status.available or not terms:
            return HistorySearchResult(items=[], query_terms=terms, status=status)
        fts_query = " OR ".join(f'"{term}"' for term in terms)
        clauses = [
            "chat_message_fts MATCH ?",
            "profile_id = ?",
            "workspace_id = ?",
            "project_id = ?",
        ]
        params: list[object] = [fts_query, profile_id, workspace_id, project_id or ""]
        if exclude_session_id:
            clauses.append("session_id != ?")
            params.append(exclude_session_id)
        params.append(max(0, min(limit, 50)))
        query_sql = (
            "SELECT message_id, session_id, role, content, created_at, bm25(chat_message_fts) AS rank "
            "FROM chat_message_fts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY rank ASC, created_at DESC, message_id ASC LIMIT ?"
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(query_sql, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            failed = HistorySearchStatus(
                available=False,
                reason=f"fts5_query_failed:{exc}",
                indexed_messages=status.indexed_messages,
            )
            return HistorySearchResult(items=[], query_terms=terms, status=failed)
        return HistorySearchResult(
            items=[
                PromptHistoryItem(
                    session_id=row["session_id"],
                    message_id=row["message_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                )
                for row in rows
            ],
            query_terms=terms,
            status=status,
        )


def default_history_search_service() -> SQLiteHistorySearchService:
    return SQLiteHistorySearchService()
