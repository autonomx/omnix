"""Character-aware Chat store adapters for JSON and SQLite persistence."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.characters import (
    InteractionSelection,
    SetSessionInteractionRequest,
    default_character_service,
    resolve_interaction_context,
)

from .models import ChatMessage, ChatSession, ChatSessionSummary, CreateChatSessionRequest
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
        interaction, character_profile = _resolve_request(
            request.interaction_mode,
            request.character_id,
            request.voice_asset_id,
            request.transcript_policy,
        )
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
        _append_character_greeting(messages, character_profile, now)
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

    @serialized_chat_mutation
    def set_session_interaction(
        self,
        session_id: str,
        request: SetSessionInteractionRequest,
    ) -> ChatSession | None:
        sessions = self._load_sessions()
        interaction, character_profile = _resolve_request(
            request.interaction_mode,
            request.character_id,
            request.voice_asset_id,
            request.transcript_policy,
        )
        now = _utcnow()
        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue
            changed_identity = (
                session.interaction_mode != interaction.interaction_mode
                or session.character_id != interaction.character_id
            )
            session.interaction_mode = interaction.interaction_mode
            session.character_id = interaction.character_id
            session.voice_asset_id = interaction.voice_asset_id
            session.read_memory = False
            session.write_memory = False
            session.shared_memory_access = "none"
            session.transcript_policy = interaction.transcript_policy
            session.character_profile_version = interaction.character_profile_version
            session.effective_identity_hash = interaction.effective_identity_hash
            if changed_identity:
                _append_character_greeting(session.messages, character_profile, now)
            session.message_count = len(session.messages)
            session.updated_at = now
            sessions[index] = session
            self._save_sessions(sessions)
            return session
        return None

    @staticmethod
    def _summary(session: ChatSession) -> ChatSessionSummary:
        payload = session.model_dump(exclude={"messages"}, mode="python")
        payload["message_count"] = len(session.messages)
        return ChatSessionSummary(**payload)


class ChatSessionStore(_CharacterSessionMixin, BaseChatSessionStore):
    pass


class SQLiteChatSessionStore(_CharacterSessionMixin, BaseSQLiteChatSessionStore):
    pass


def default_chat_store() -> ChatSessionStore | SQLiteChatSessionStore:
    if chat_sqlite_store_enabled():
        return SQLiteChatSessionStore()
    return ChatSessionStore()


def _resolve_request(
    interaction_mode: str,
    character_id: str | None,
    voice_asset_id: str | None,
    transcript_policy: str,
):
    selection = InteractionSelection(
        interaction_mode=interaction_mode,
        character_id=character_id,
        voice_asset_id=voice_asset_id,
        read_memory=False,
        write_memory=False,
        shared_memory_access="none",
        transcript_policy=transcript_policy,
    )
    character_profile = None
    if interaction_mode == "character":
        character_profile = default_character_service().resolve_snapshot(character_id or "")
    return resolve_interaction_context(selection, character=character_profile), character_profile


def _append_character_greeting(messages: list[ChatMessage], character_profile, now: str) -> None:
    if character_profile is None or not character_profile.default_greeting.strip():
        return
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
