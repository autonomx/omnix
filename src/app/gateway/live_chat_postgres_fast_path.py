"""Use targeted PostgreSQL operations before live chat provider streaming.

The compatibility ChatStore contract historically loaded every recent session and
all of their messages, then saved the entire workspace, to append one live voice
user turn. That work sits directly on the first-token path. This hook preserves
the public store contract while limiting the live runtime mutation to the active
session and one append-only message transaction.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from app.chat.character_store import _find_idempotent_user_turn, _start_assistant_turn
from app.chat.concurrency import serialized_chat_mutation
from app.chat.memory_commands import parse_memory_command
from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.chat.store import _context_source_summaries
from app.persistence.chat_runtime_compat import (
    PostgresCharacterChatSessionStore,
    PostgresChatSessionStore,
)
from app.persistence.unit_of_work import unit_of_work

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_postgres_fast_path_installed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_single_session(store: Any, session_id: str) -> ChatSession | None:
    """Load only the requested session and its bounded transcript."""
    adapter = store._repository
    with unit_of_work(adapter.database) as work:
        record = work.chats.get_session(adapter.context, session_id)
        if record is None:
            work.rollback()
            return None
        messages = work.chats.list_messages(
            adapter.context,
            session_id,
            limit=500,
            after_position=-1,
        )
        session = adapter._to_session(record, messages)
        work.rollback()
    return session


def _persist_user_turn(store: Any, session: ChatSession, message: ChatMessage) -> bool:
    """Update active session routing fields and append exactly one user message."""
    adapter = store._repository
    with unit_of_work(adapter.database) as work:
        updated = work.connection.execute(
            """
            UPDATE omnix_chat_sessions
               SET title = %s,
                   provider_id = %s,
                   model_id = %s
             WHERE id = %s
               AND workspace_id = %s
               AND status = 'active'
            RETURNING id
            """,
            (
                session.title,
                session.provider_id,
                session.model_id,
                session.id,
                adapter.context.workspace_id,
            ),
        ).fetchone()
        if updated is None:
            work.rollback()
            return False
        work.chats.append_message(
            adapter.context,
            session.id,
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
                "metadata": dict(message.metadata),
            },
        )
        work.commit()
    return True


def _begin_user_message_fast(
    self: PostgresCharacterChatSessionStore,
    session_id: str,
    request: SendChatMessageRequest,
    *,
    context_items: list[dict[str, Any]] | None = None,
    context_diagnostics: dict[str, Any] | None = None,
) -> tuple[ChatSession, ChatMessage] | None:
    started = time.perf_counter()
    load_started = time.perf_counter()
    session = _load_single_session(self, session_id)
    load_ms = (time.perf_counter() - load_started) * 1000.0
    if session is None:
        return None

    existing = _find_idempotent_user_turn(session, request.user_turn_id)
    if existing is not None:
        stream_log(
            "gateway-live-chat-first-token",
            "runtime",
            "live_chat_user_turn_fast_path_idempotent",
            load_ms=round(load_ms, 3),
            total_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return existing

    now = _utcnow()
    turn_context = context_items or []
    context_sources = _context_source_summaries(turn_context)
    message_metadata: dict[str, Any] = {
        "generation_status": "running",
        "agent_mode": request.agent_mode,
    }
    if context_sources:
        message_metadata["context_sources"] = context_sources
    if context_diagnostics:
        message_metadata["context_diagnostics"] = context_diagnostics

    message = ChatMessage(
        id=f"msg:{uuid.uuid4().hex}",
        role="user",
        content=request.content.strip(),
        created_at=now,
        metadata=message_metadata,
    )
    command = parse_memory_command(message.content)
    if command is not None:
        message.metadata["memory_command"] = command.model_dump(mode="json")

    coordinator_started = time.perf_counter()
    _start_assistant_turn(session, message, request)
    message.metadata["segment_id"] = session.active_segment_id
    coordinator_ms = (time.perf_counter() - coordinator_started) * 1000.0

    session.messages.append(message)
    session.provider_id = request.provider_id or session.provider_id
    session.model_id = request.model_id or session.model_id
    session.message_count = len(session.messages)
    if session.title.strip().lower() in {"new chat", "new chat..."}:
        session.title = message.content[:48] or "New chat"
    session.updated_at = now

    persist_started = time.perf_counter()
    try:
        persisted = _persist_user_turn(self, session, message)
    except Exception as exc:
        stream_log(
            "gateway-live-chat-first-token",
            "runtime",
            "live_chat_user_turn_fast_path_failed",
            error_type=type(exc).__name__,
            load_ms=round(load_ms, 3),
            coordinator_ms=round(coordinator_ms, 3),
            total_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        raise
    persist_ms = (time.perf_counter() - persist_started) * 1000.0
    if not persisted:
        return None

    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_user_turn_fast_path_completed",
        load_ms=round(load_ms, 3),
        coordinator_ms=round(coordinator_ms, 3),
        persist_ms=round(persist_ms, 3),
        total_ms=round((time.perf_counter() - started) * 1000.0, 3),
        session_message_count=session.message_count,
    )
    return session, message


def install_live_chat_postgres_fast_path() -> None:
    """Install targeted session reads and user-turn persistence once."""
    if getattr(PostgresCharacterChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_get_session = PostgresChatSessionStore.get_session
    original_begin_user_message = PostgresCharacterChatSessionStore.begin_user_message

    @wraps(original_get_session)
    def patched_get_session(
        self: PostgresChatSessionStore,
        session_id: str,
    ) -> ChatSession | None:
        return _load_single_session(self, session_id)

    patched_begin_user_message = wraps(original_begin_user_message)(
        serialized_chat_mutation(_begin_user_message_fast)
    )

    PostgresChatSessionStore.get_session = patched_get_session
    PostgresCharacterChatSessionStore.begin_user_message = patched_begin_user_message
    setattr(PostgresCharacterChatSessionStore, _HOOK_SENTINEL, True)
