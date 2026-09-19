"""Use targeted PostgreSQL operations for live chat streaming.

The compatibility ChatStore contract historically loaded every recent session and
all messages, then saved the entire workspace, to append or complete one live
voice turn. That work sat on the first-token and terminal-delivery paths. This
hook preserves the public store contract while limiting live runtime mutations
to the active session and append-only message transactions.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from threading import Lock, RLock
from typing import Any

from app.chat.assistant_turns import default_assistant_turn_coordinator
from app.chat.character_store import _find_idempotent_user_turn, _start_assistant_turn
from app.chat.memory_commands import parse_memory_command
from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.chat.retention_policy import transcript_retention_allowed
from app.chat.store import _context_source_summaries
from app.persistence.chat_runtime_compat import (
    PostgresCharacterChatSessionStore,
    PostgresChatSessionStore,
)
from app.persistence.unit_of_work import unit_of_work

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_postgres_fast_path_installed"
_SESSION_LOCKS_GUARD = Lock()
_SESSION_LOCKS: dict[str, tuple[RLock, int]] = {}


@contextmanager
def _live_session_mutation(session_id: str) -> Iterator[float]:
    """Serialize live PostgreSQL writes only with their own chat session.

    The regular Chat store has a process-wide lock because its JSON backend
    rewrites the complete collection. The live PostgreSQL fast path writes one
    session atomically, so retaining that global lock made a completed reply
    wait behind unrelated chat and memory work. Entries are removed once their
    last holder or waiter leaves to keep the registry bounded.
    """
    key = session_id.strip() or "__unknown_session__"
    with _SESSION_LOCKS_GUARD:
        current = _SESSION_LOCKS.get(key)
        if current is None:
            lock, users = RLock(), 0
        else:
            lock, users = current
        _SESSION_LOCKS[key] = (lock, users + 1)

    wait_started = time.perf_counter()
    lock.acquire()
    wait_ms = (time.perf_counter() - wait_started) * 1000.0
    try:
        yield wait_ms
    finally:
        lock.release()
        with _SESSION_LOCKS_GUARD:
            current = _SESSION_LOCKS.get(key)
            if current is not None:
                current_lock, users = current
                if current_lock is lock:
                    if users <= 1:
                        _SESSION_LOCKS.pop(key, None)
                    else:
                        _SESSION_LOCKS[key] = (lock, users - 1)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _assistant_message_id(session_id: str, user_message_id: str) -> str:
    """Return one stable assistant message ID for an originating user turn."""
    identity = f"omnix-live-assistant:{session_id}:{user_message_id}"
    return f"msg:{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex}"


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


def _persist_assistant_completion(
    store: Any,
    session: ChatSession,
    user_message: ChatMessage,
    *,
    content: str,
    metadata: dict[str, Any],
    assistant_turn_id: str,
    generation_status: str,
    assistant_turn_payload: dict[str, Any] | None,
) -> tuple[bool, bool]:
    """Persist user terminal metadata and at most one assistant reply atomically."""
    adapter = store._repository
    user_metadata = dict(user_message.metadata)
    user_metadata["generation_status"] = generation_status
    if assistant_turn_payload is not None:
        user_metadata["assistant_turn"] = assistant_turn_payload

    assistant_metadata = {
        **metadata,
        "segment_id": session.active_segment_id,
        "generation_status": generation_status,
    }
    if assistant_turn_id:
        assistant_metadata["assistant_turn_id"] = assistant_turn_id
    if generation_status == "interrupted":
        assistant_metadata["delivery_status"] = "interrupted"

    assistant_id = _assistant_message_id(session.id, user_message.id)
    generated = content.strip()
    allow_transcript = transcript_retention_allowed(session)
    with unit_of_work(adapter.database) as work:
        updated = work.connection.execute(
            """
            UPDATE omnix_chat_messages
               SET metadata = %s::jsonb
             WHERE id = %s
               AND workspace_id = %s
               AND session_id = %s
               AND role = 'user'
            RETURNING id
            """,
            (
                _json(user_metadata),
                user_message.id,
                adapter.context.workspace_id,
                session.id,
            ),
        ).fetchone()
        if updated is None:
            work.rollback()
            return False, False

        existing = work.connection.execute(
            """
            SELECT id
              FROM omnix_chat_messages
             WHERE workspace_id = %s
               AND session_id = %s
               AND (
                    id = %s
                    OR (
                        role = 'assistant'
                        AND metadata->>'assistant_turn_id' = %s
                    )
               )
             LIMIT 1
            """,
            (
                adapter.context.workspace_id,
                session.id,
                assistant_id,
                assistant_turn_id,
            ),
        ).fetchone()
        assistant_already_present = existing is not None
        assistant_appended = False
        if generated and allow_transcript and not assistant_already_present:
            work.chats.append_message(
                adapter.context,
                session.id,
                {
                    "id": assistant_id,
                    "role": "assistant",
                    "content": generated,
                    "created_at": _utcnow(),
                    "metadata": assistant_metadata,
                },
            )
            assistant_appended = True
        else:
            work.connection.execute(
                """
                UPDATE omnix_chat_sessions
                   SET revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s
                   AND workspace_id = %s
                   AND status = 'active'
                """,
                (session.id, adapter.context.workspace_id),
            )
        work.commit()
    return assistant_appended, assistant_already_present


def _completed_session_snapshot(
    session: ChatSession,
    user_message: ChatMessage,
    *,
    content: str,
    metadata: dict[str, Any],
    assistant_turn_id: str,
    generation_status: str,
    assistant_turn_payload: dict[str, Any] | None,
    assistant_appended: bool,
) -> ChatSession:
    """Update the already-loaded session for the normal append-success path."""
    user_metadata = dict(user_message.metadata)
    user_metadata["generation_status"] = generation_status
    if assistant_turn_payload is not None:
        user_metadata["assistant_turn"] = assistant_turn_payload
    user_message.metadata = user_metadata

    if assistant_appended:
        assistant_metadata = {
            **metadata,
            "segment_id": session.active_segment_id,
            "generation_status": generation_status,
        }
        if assistant_turn_id:
            assistant_metadata["assistant_turn_id"] = assistant_turn_id
        if generation_status == "interrupted":
            assistant_metadata["delivery_status"] = "interrupted"
        assistant_message = ChatMessage(
            id=_assistant_message_id(session.id, user_message.id),
            role="assistant",
            content=content.strip(),
            created_at=_utcnow(),
            metadata=assistant_metadata,
        )
        session.messages.append(assistant_message)
        session.message_count = len(session.messages)
        session.updated_at = assistant_message.created_at
    return session


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
        "coding_approval_policy": request.coding_approval_policy,
    }
    if request.image_data_urls:
        message_metadata["image_data_urls"] = list(request.image_data_urls)
        message_metadata["image_data_url"] = request.image_data_urls[0]
    if request.text_attachment:
        message_metadata["text_attachment"] = request.text_attachment.model_dump()
    if request.research_mode is not None:
        message_metadata["research_mode"] = request.research_mode
    if request.workspace_root:
        message_metadata["workspace_root"] = request.workspace_root
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


def _complete_streamed_reply_fast(
    self: PostgresCharacterChatSessionStore,
    session_id: str,
    user_message_id: str,
    content: str,
    metadata: dict[str, Any],
    *,
    lock_wait_ms: float = 0.0,
) -> ChatSession | None:
    """Complete one streamed reply without a workspace-wide compatibility save."""
    started = time.perf_counter()
    stage = "load_session"
    try:
        session = _load_single_session(self, session_id)
        if session is None:
            return None
        user_message = next(
            (message for message in session.messages if message.id == user_message_id),
            None,
        )
        if user_message is None:
            stream_log(
                "gateway-live-chat-completion",
                "runtime",
                "live_chat_assistant_completion_missing_user",
                session_found=True,
            )
            return session

        assistant_turn_id = str(
            user_message.metadata.get("assistant_turn_id")
            or metadata.get("assistant_turn_id")
            or ""
        ).strip()
        coordinator = default_assistant_turn_coordinator()
        turn = coordinator.get(assistant_turn_id) if assistant_turn_id else None
        if turn is not None and not turn.terminal:
            coordinator.try_complete(assistant_turn_id)
            turn = coordinator.get(assistant_turn_id)
        if turn is not None and turn.lifecycle == "interrupted":
            generation_status = "interrupted"
            coordinator.mark_provider_cancelled(assistant_turn_id)
            turn = coordinator.get(assistant_turn_id)
        elif turn is not None and turn.lifecycle == "failed":
            generation_status = "failed"
        else:
            generation_status = "completed"

        stage = "persist_completion"
        persist_started = time.perf_counter()
        assistant_appended, assistant_already_present = _persist_assistant_completion(
            self,
            session,
            user_message,
            content=content,
            metadata=dict(metadata),
            assistant_turn_id=assistant_turn_id,
            generation_status=generation_status,
            assistant_turn_payload=(
                turn.model_dump(mode="json") if turn is not None else None
            ),
        )
        persist_ms = (time.perf_counter() - persist_started) * 1000.0
        if assistant_already_present:
            stage = "reload_session"
            completed = _load_single_session(self, session_id)
            if completed is None:
                return None
        else:
            completed = _completed_session_snapshot(
                session,
                user_message,
                content=content,
                metadata=metadata,
                assistant_turn_id=assistant_turn_id,
                generation_status=generation_status,
                assistant_turn_payload=(
                    turn.model_dump(mode="json") if turn is not None else None
                ),
                assistant_appended=assistant_appended,
            )
        if generation_status == "completed":
            stage = "post_turn_maintenance"
            maintenance_started = time.perf_counter()
            self._run_post_turn_maintenance(completed, user_message_id)
            maintenance_ms = (time.perf_counter() - maintenance_started) * 1000.0
        else:
            maintenance_ms = 0.0

        stream_log(
            "gateway-live-chat-completion",
            "runtime",
            "live_chat_assistant_completion_fast_path_completed",
            assistant_appended=assistant_appended,
            assistant_already_present=assistant_already_present,
            content_chars=len(content.strip()),
            generation_status=generation_status,
            lock_wait_ms=round(lock_wait_ms, 3),
            persist_ms=round(persist_ms, 3),
            post_turn_maintenance_ms=round(maintenance_ms, 3),
            total_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return completed
    except Exception as exc:
        stream_log(
            "gateway-live-chat-completion",
            "runtime",
            "live_chat_assistant_completion_fast_path_failed",
            stage=stage,
            error_type=type(exc).__name__,
            content_chars=len(content.strip()),
            total_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        raise


def install_live_chat_postgres_fast_path() -> None:
    """Install targeted session reads and turn persistence once."""
    if getattr(PostgresCharacterChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_get_session = PostgresChatSessionStore.get_session
    original_begin_user_message = PostgresCharacterChatSessionStore.begin_user_message
    original_complete_streamed_reply = (
        PostgresCharacterChatSessionStore.complete_streamed_reply
    )

    @wraps(original_get_session)
    def patched_get_session(
        self: PostgresChatSessionStore,
        session_id: str,
    ) -> ChatSession | None:
        return _load_single_session(self, session_id)

    @wraps(original_begin_user_message)
    def patched_begin_user_message(
        self: PostgresCharacterChatSessionStore,
        session_id: str,
        request: SendChatMessageRequest,
        **kwargs: Any,
    ) -> tuple[ChatSession, ChatMessage] | None:
        with _live_session_mutation(session_id):
            return _begin_user_message_fast(self, session_id, request, **kwargs)

    @wraps(original_complete_streamed_reply)
    def patched_complete_streamed_reply(
        self: PostgresCharacterChatSessionStore,
        session_id: str,
        user_message_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> ChatSession | None:
        with _live_session_mutation(session_id) as lock_wait_ms:
            return _complete_streamed_reply_fast(
                self,
                session_id,
                user_message_id,
                content,
                metadata,
                lock_wait_ms=lock_wait_ms,
            )

    PostgresChatSessionStore.get_session = patched_get_session
    PostgresCharacterChatSessionStore.begin_user_message = patched_begin_user_message
    PostgresCharacterChatSessionStore.complete_streamed_reply = (
        patched_complete_streamed_reply
    )
    setattr(PostgresCharacterChatSessionStore, _HOOK_SENTINEL, True)
