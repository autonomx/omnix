"""Backend-owned per-session setting for generative UI in replies (chat generative UI, GUI-3.1)."""
from __future__ import annotations

from app.conversation.contracts import RichRepliesMode

from .models import ChatSession
from .store import ChatSessionStore


def update_conversation_rich_replies(
    store: ChatSessionStore,
    session_id: str,
    mode: RichRepliesMode | None,
) -> ChatSession | None:
    """Persist a session's rich-replies setting without changing message history."""

    session = store.get_session(session_id)
    if session is None:
        return None
    session.rich_replies = mode
    store._save_session(session)  # noqa: SLF001 - one targeted session mutation
    return session
