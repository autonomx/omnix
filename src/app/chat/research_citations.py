"""Citation validation for completed research-backed chat replies."""
from __future__ import annotations

from typing import Any

from app.research.evidence import (
    citation_labels,
    render_answer_with_compatibility_fallback,
    source_manifest_id,
)

from .concurrency import serialized_chat_mutation
from .models import ChatSession
from .store import ChatSessionStore


@serialized_chat_mutation
def validate_completed_research_reply(
    store: ChatSessionStore,
    session_id: str,
    user_message_id: str,
    context_items: list[dict[str, Any]],
    *,
    show_diagnostics: bool = True,
) -> ChatSession | None:
    labels = citation_labels(context_items)
    if not labels:
        return store.get_session(session_id)
    sessions = store._load_sessions()  # noqa: SLF001 - same bounded persistence domain
    for session_index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        assistant = next(
            (
                message
                for message in session.messages
                if message.role == "assistant"
                and message.metadata.get("reply_to_message_id") == user_message_id
            ),
            None,
        )
        if assistant is None:
            user_index = next(
                (
                    index
                    for index, message in enumerate(session.messages)
                    if message.id == user_message_id
                ),
                None,
            )
            if user_index is None:
                return session
            assistant = next(
                (
                    message
                    for message in session.messages[user_index + 1 :]
                    if message.role == "assistant"
                ),
                None,
            )
        if assistant is None:
            return session
        rendered = render_answer_with_compatibility_fallback(assistant.content, labels)
        assistant.content = rendered.content
        assistant.metadata.update(
            {
                "research_mode": "quick",
                "research_status": "completed",
                "research_diagnostics_enabled": show_diagnostics,
                "source_manifest_id": source_manifest_id(context_items),
                "citation_validation": rendered.validation.model_dump(mode="json"),
            }
        )
        session.updated_at = assistant.created_at
        sessions[session_index] = session
        store._save_sessions(sessions)  # noqa: SLF001 - same bounded persistence domain
        return session
    return None
