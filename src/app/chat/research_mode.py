"""Backend-owned conversation research-mode persistence."""
from __future__ import annotations

from app.research import ResearchMode

from .models import ChatSession
from .store import ChatSessionStore


def update_conversation_research_mode(
    store: ChatSessionStore,
    session_id: str,
    mode: ResearchMode | None,
) -> ChatSession | None:
    """Persist a conversation override without changing message history."""

    sessions = store._load_sessions()  # noqa: SLF001 - same bounded persistence domain
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        session.research_mode_override = mode
        sessions[index] = session
        store._save_sessions(sessions)  # noqa: SLF001 - same bounded persistence domain
        return session
    return None
