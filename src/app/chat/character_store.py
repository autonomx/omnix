"""Character-aware Chat store adapters for JSON and SQLite persistence."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.characters import (
    InteractionSelection,
    default_character_service,
    resolve_interaction_context,
)

from .models import ChatMessage, ChatSession, CreateChatSessionRequest
from .prompt_store import ChatSessionStore as BaseChatSessionStore, chat_sqlite_store_enabled
from .sqlite_store import SQLiteChatSessionStore as BaseSQLiteChatSessionStore
from .store import serialized_chat_mutation


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class _CharacterSessionMixin:
    @serialized_chat_mutation
    def create_session(self, request: CreateChatSessionRequest) -> ChatSession:
        now = _utcnow()
        title = (request.title or "New chat").strip() or "New chat"
        selection = InteractionSelection(
            interaction_mode=request.interaction_mode,
            character_id=request.character_id,
            voice_asset_id=request.voice_asset_id,
            read_memory=False,
            write_memory=False,
            shared_memory_access="none",
            transcript_policy=request.transcript_policy,
        )
        character_profile = None
        if request.interaction_mode == "character":
            character_profile = default_character_service().resolve_snapshot(request.character_id or "")
        interaction = resolve_interaction_context(selection, character=character_profile)

        messages: list[ChatMessage] = []
        if request.interaction_mode == "system" and request.system_prompt:
            messages.append(
                ChatMessage(
                    id=f"msg:{uuid.uuid4().hex}",
                    role="system",
                    content=request.system_prompt,
                    created_at=now,
                    metadata={"source": "chat_session_request"},
                )
            )
        if character_profile and character_profile.default_greeting.strip():
            messages.append(
                ChatMessage(
                    id=f"msg:{uuid.uuid4().hex}",
                    role="assistant",
                    content=character_profile.default_greeting.strip(),
                    created_at=now,
                    metadata={
                        "source": "character_profile_greeting",
                        "character_id": character_profile.id,
                        "character_profile_version": character_profile.version,
                    },
                )
            )

        session = ChatSession(
            id=f"chat:{uuid.uuid4().hex}",
            title=title,
            provider_id=request.provider_id,
            model_id=request.model_id,
            interaction_mode=interaction.interaction_mode,
            character_id=interaction.character_id,
            voice_asset_id=interaction.voice_asset_id,
            read_memory=False,
            write_memory=False,
            shared_memory_access="none",
            transcript_policy=interaction.transcript_policy,
            character_profile_version=interaction.character_profile_version,
            effective_identity_hash=interaction.effective_identity_hash,
            message_count=len(messages),
            messages=messages,
            created_at=now,
            updated_at=now,
        )
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session


class ChatSessionStore(_CharacterSessionMixin, BaseChatSessionStore):
    pass


class SQLiteChatSessionStore(_CharacterSessionMixin, BaseSQLiteChatSessionStore):
    pass


def default_chat_store() -> ChatSessionStore | SQLiteChatSessionStore:
    if chat_sqlite_store_enabled():
        return SQLiteChatSessionStore()
    return ChatSessionStore()
