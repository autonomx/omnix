"""Chat persistence helpers for durable research jobs."""
from __future__ import annotations

from typing import Any

from .models import ChatMessage, ChatSession
from .store import ChatSessionStore


def link_user_message_to_research_job(
    store: ChatSessionStore,
    session_id: str,
    message_id: str,
    job_id: str,
) -> tuple[ChatSession, ChatMessage] | None:
    metadata = {
        "research_mode": "deep",
        "research_status": "queued",
        "research_job_id": job_id,
    }
    targeted_update = getattr(store, "update_user_message_metadata", None)
    if callable(targeted_update):
        changed = targeted_update(
            session_id=session_id,
            message_id=message_id,
            metadata=metadata,
        )
        if not changed:
            return None
        sessions = store._load_sessions()  # noqa: SLF001 - same bounded persistence domain
        for session in sessions:
            if session.id != session_id:
                continue
            for message in session.messages:
                if message.id == message_id:
                    return session, message
        return None

    sessions = store._load_sessions()  # noqa: SLF001 - same bounded persistence domain
    for session_index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id != message_id:
                continue
            message.metadata.update(metadata)
            sessions[session_index] = session
            store._save_sessions(sessions)  # noqa: SLF001 - same bounded persistence domain
            return session, message
    return None
