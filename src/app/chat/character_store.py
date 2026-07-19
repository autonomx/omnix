"""Character-aware Chat stores with durable provider-context segments."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.assistant_memory import default_memory_service, resolve_session_memory_scope
from app.characters import (
    InteractionSelection,
    SetSessionInteractionRequest,
    default_character_service,
    resolve_interaction_context,
)

from .assistant_turns import default_assistant_turn_coordinator
from .models import ChatMessage, ChatSession, ChatSessionSummary, CreateChatSessionRequest, SendChatMessageRequest
from .prompt_store import ChatSessionStore as BaseChatSessionStore, chat_sqlite_store_enabled
from .sqlite_store import InMemoryChatSessionStore as BaseInMemoryChatSessionStore
from .store import serialized_chat_mutation


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class _CharacterSessionMixin:
    @serialized_chat_mutation
    def create_session(self, request: CreateChatSessionRequest) -> ChatSession:
        now = _utcnow()
        session_id = f"chat:{uuid.uuid4().hex}"
        interaction, character_profile = _resolve_request(
            request.interaction_mode,
            request.character_id,
            request.voice_asset_id,
            request.transcript_policy,
            request.read_memory if request.interaction_mode == "character" else False,
            request.write_memory if request.interaction_mode == "character" else False,
            request.shared_memory_access if request.interaction_mode == "character" else "none",
        )
        segment = _character_repository().create_segment(
            session_id=session_id,
            interaction_mode=interaction.interaction_mode,
            character_id=interaction.character_id,
            profile_version=interaction.character_profile_version,
            transcript_policy=interaction.transcript_policy,
            read_memory=interaction.read_memory,
            write_memory=interaction.write_memory,
            shared_memory_access=interaction.shared_memory_access,
        )
        messages: list[ChatMessage] = []
        if request.interaction_mode == "system" and request.system_prompt:
            messages.append(ChatMessage(
                id=f"msg:{uuid.uuid4().hex}", role="system", content=request.system_prompt,
                created_at=now, metadata={"source": "chat_session_request", "segment_id": segment.id},
            ))
        _append_character_greeting(messages, character_profile, now, segment.id)
        session = ChatSession(
            id=session_id,
            title=(request.title or "New chat").strip() or "New chat",
            provider_id=request.provider_id,
            model_id=request.model_id,
            interaction_mode=interaction.interaction_mode,
            character_id=interaction.character_id,
            voice_asset_id=interaction.voice_asset_id,
            read_memory=interaction.read_memory,
            write_memory=interaction.write_memory,
            shared_memory_access=interaction.shared_memory_access,
            transcript_policy=interaction.transcript_policy,
            active_segment_id=segment.id,
            character_profile_version=interaction.character_profile_version,
            effective_identity_hash=interaction.effective_identity_hash,
            message_count=len(messages), messages=messages, created_at=now, updated_at=now,
        )
        _attach_character_snapshot(session)
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session

    @serialized_chat_mutation
    def set_session_interaction(self, session_id: str, request: SetSessionInteractionRequest) -> ChatSession | None:
        sessions = self._load_sessions()
        interaction, character_profile = _resolve_request(
            request.interaction_mode,
            request.character_id,
            request.voice_asset_id,
            request.transcript_policy,
            request.read_memory if request.interaction_mode == "character" else False,
            request.write_memory if request.interaction_mode == "character" else False,
            request.shared_memory_access if request.interaction_mode == "character" else "none",
        )
        now = _utcnow()
        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue
            context_changed = (
                session.interaction_mode != interaction.interaction_mode
                or session.character_id != interaction.character_id
                or session.transcript_policy != interaction.transcript_policy
                or session.read_memory != interaction.read_memory
                or session.write_memory != interaction.write_memory
                or session.shared_memory_access != interaction.shared_memory_access
            )
            if context_changed:
                carryover = _neutral_topic_carryover(session) if request.continue_topic else None
                if session.active_segment_id:
                    _character_repository().close_segment(session.active_segment_id)
                segment = _character_repository().create_segment(
                    session_id=session.id,
                    interaction_mode=interaction.interaction_mode,
                    character_id=interaction.character_id,
                    profile_version=interaction.character_profile_version,
                    transcript_policy=interaction.transcript_policy,
                    read_memory=interaction.read_memory,
                    write_memory=interaction.write_memory,
                    shared_memory_access=interaction.shared_memory_access,
                    carryover_summary=carryover,
                )
                session.active_segment_id = segment.id
                session.memory_snapshot_id = None
                session.memory_snapshot_revision = None
                session.memory_record_count = 0
                session.memory_last_refreshed_at = None
                _append_character_greeting(session.messages, character_profile, now, segment.id)
            session.interaction_mode = interaction.interaction_mode
            session.character_id = interaction.character_id
            session.voice_asset_id = interaction.voice_asset_id
            session.read_memory = interaction.read_memory
            session.write_memory = interaction.write_memory
            session.shared_memory_access = interaction.shared_memory_access
            session.transcript_policy = interaction.transcript_policy
            session.character_profile_version = interaction.character_profile_version
            session.effective_identity_hash = interaction.effective_identity_hash
            _attach_character_snapshot(session)
            session.message_count = len(session.messages)
            session.updated_at = now
            sessions[index] = session
            self._save_sessions(sessions)
            return session
        return None

    @serialized_chat_mutation
    def append_user_message(self, session_id: str, request: SendChatMessageRequest, *, context_items: list[dict[str, Any]] | None = None, context_diagnostics: dict[str, Any] | None = None):
        existing = _find_idempotent_user_turn(self.get_session(session_id), request.user_turn_id)
        if existing is not None:
            return existing
        result = super().append_user_message(session_id, request, context_items=context_items, context_diagnostics=context_diagnostics)
        if result is None:
            return None
        session, user_message = result
        record = _start_assistant_turn(session, user_message, request)
        record = default_assistant_turn_coordinator().mark_streaming(record.assistant_turn_id) or record
        default_assistant_turn_coordinator().try_complete(record.assistant_turn_id)
        _tag_turn_and_save(self, session, user_message.id, record.assistant_turn_id, record.user_turn_id, record.speech_segment_id)
        return session, user_message

    @serialized_chat_mutation
    def begin_user_message(self, session_id: str, request: SendChatMessageRequest, *, context_items: list[dict[str, Any]] | None = None, context_diagnostics: dict[str, Any] | None = None):
        existing = _find_idempotent_user_turn(self.get_session(session_id), request.user_turn_id)
        if existing is not None:
            return existing
        result = super().begin_user_message(session_id, request, context_items=context_items, context_diagnostics=context_diagnostics)
        if result is None:
            return None
        session, user_message = result
        record = _start_assistant_turn(session, user_message, request)
        user_message.metadata.update({
            "segment_id": session.active_segment_id,
            "user_turn_id": record.user_turn_id,
            "speech_segment_id": record.speech_segment_id,
            "assistant_turn_id": record.assistant_turn_id,
            "assistant_turn": record.model_dump(mode="json"),
        })
        self._save_sessions(_replace_session(self._load_sessions(), session))
        return session, user_message

    def stream_provider_reply_chunks(self, session: ChatSession, user_message: ChatMessage, **kwargs):
        coordinator = default_assistant_turn_coordinator()
        assistant_turn_id = str(user_message.metadata.get("assistant_turn_id") or "").strip()
        if assistant_turn_id:
            coordinator.mark_streaming(assistant_turn_id)
        generated_parts: list[str] = []
        saw_completion = False
        try:
            for event in super().stream_provider_reply_chunks(session, user_message, **kwargs):
                if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                    break
                if event.get("type") == "text_chunk" and isinstance(event.get("text"), str):
                    generated_parts.append(str(event["text"]))
                if event.get("type") == "complete":
                    saw_completion = True
                    if assistant_turn_id:
                        event = {
                            **event,
                            "metadata": {
                                **dict(event.get("metadata") or {}),
                                "assistant_turn_id": assistant_turn_id,
                            },
                        }
                yield event
        except GeneratorExit:
            if assistant_turn_id:
                coordinator.request_cancel(assistant_turn_id, "client_disconnected")
                coordinator.mark_provider_cancelled(assistant_turn_id)
            raise
        except Exception:
            if assistant_turn_id:
                coordinator.mark_failed(assistant_turn_id)
            raise
        finally:
            if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                coordinator.mark_provider_cancelled(assistant_turn_id)
            elif assistant_turn_id and not saw_completion:
                coordinator.request_cancel(assistant_turn_id, "stream_closed_before_completion")
                coordinator.mark_provider_cancelled(assistant_turn_id)
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            yield {
                "type": "complete",
                "content": " ".join(part.strip() for part in generated_parts if part.strip()).strip(),
                "metadata": {
                    "generation_status": "interrupted",
                    "delivery_status": "interrupted",
                    "assistant_turn_id": assistant_turn_id,
                },
            }

    @serialized_chat_mutation
    def complete_streamed_reply(self, session_id: str, user_message_id: str, content: str, metadata: dict[str, Any]) -> ChatSession | None:
        before = self.get_session(session_id)
        segment_id = before.active_segment_id if before else None
        user_message = next((message for message in before.messages if message.id == user_message_id), None) if before else None
        assistant_turn_id = (
            str(user_message.metadata.get("assistant_turn_id") or "").strip()
            if user_message
            else str(metadata.get("assistant_turn_id") or "").strip()
        )
        coordinator = default_assistant_turn_coordinator()
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            return _persist_interrupted_reply(
                self,
                session_id=session_id,
                user_message_id=user_message_id,
                assistant_turn_id=assistant_turn_id,
                content=content,
                metadata={**metadata, "segment_id": segment_id},
            )
        if assistant_turn_id and not coordinator.try_complete(assistant_turn_id):
            return self.get_session(session_id)
        session = super().complete_streamed_reply(
            session_id,
            user_message_id,
            content,
            {**metadata, "segment_id": segment_id, **({"assistant_turn_id": assistant_turn_id} if assistant_turn_id else {})},
        )
        if session is None:
            return None
        for message in session.messages:
            if message.id == user_message_id:
                message.metadata["segment_id"] = segment_id
                if assistant_turn_id:
                    turn = coordinator.get(assistant_turn_id)
                    if turn is not None:
                        message.metadata["assistant_turn"] = turn.model_dump(mode="json")
                break
        self._save_sessions(_replace_session(self._load_sessions(), session))
        return session

    @staticmethod
    def _summary(session: ChatSession) -> ChatSessionSummary:
        payload = session.model_dump(exclude={"messages"}, mode="python")
        payload["message_count"] = len(session.messages)
        return ChatSessionSummary(**payload)


class ChatSessionStore(_CharacterSessionMixin, BaseChatSessionStore):
    pass


class InMemoryChatSessionStore(_CharacterSessionMixin, BaseInMemoryChatSessionStore):
    pass


def default_chat_store() -> ChatSessionStore | InMemoryChatSessionStore:
    return InMemoryChatSessionStore() if chat_sqlite_store_enabled() else ChatSessionStore()


def _character_repository():
    return default_character_service().repository


def _resolve_request(
    interaction_mode: str,
    character_id: str | None,
    voice_asset_id: str | None,
    transcript_policy: str,
    read_memory: bool,
    write_memory: bool,
    shared_memory_access: str,
):
    selection = InteractionSelection(
        interaction_mode=interaction_mode,
        character_id=character_id,
        voice_asset_id=voice_asset_id,
        read_memory=read_memory,
        write_memory=write_memory,
        shared_memory_access=shared_memory_access,
        transcript_policy=transcript_policy,
    )
    character_profile = default_character_service().resolve_snapshot(character_id or "") if interaction_mode == "character" else None
    return resolve_interaction_context(selection, character=character_profile), character_profile


def _attach_character_snapshot(session: ChatSession) -> None:
    if session.interaction_mode != "character" or not session.read_memory or session.memory_snapshot_id:
        return
    snapshot = default_memory_service().create_session_snapshot(
        resolve_session_memory_scope(session), token_budget=4_000
    )
    session.memory_snapshot_id = snapshot.id
    session.memory_snapshot_revision = snapshot.revision
    session.memory_record_count = len(snapshot.items)
    session.memory_last_refreshed_at = snapshot.created_at


def _append_character_greeting(messages: list[ChatMessage], character_profile, now: str, segment_id: str) -> None:
    if character_profile is None or not character_profile.default_greeting.strip():
        return
    messages.append(ChatMessage(
        id=f"msg:{uuid.uuid4().hex", role="assistant",
        content=character_profile.default_greeting.strip(), created_at=now,
        metadata={"source": "character_profile_greeting", "character_id": character_profile.id, "character_profile_version": character_profile.version, "segment_id": segment_id},
    ))


def _neutral_topic_carryover(session: ChatSession) -> str | None:
    user_messages = [message.content.strip() for message in session.messages if message.role == "user" and (not session.active_segment_id or message.metadata.get("segment_id") == session.active_segment_id) and message.content.strip()][-4:]
    if not user_messages:
        return None
    return "\n".join(["User topics carried from the previous identity segment:", *(f"- {content[:500]}" for content in user_messages)])[:2400]


def _find_idempotent_user_turn(session: ChatSession | None, user_turn_id: str | None):
    if session is None or not user_turn_id:
        return None
    message = next(
        (item for item in session.messages if item.role == "user" and item.metadata.get("user_turn_id") == user_turn_id),
        None,
    )
    return (session, message) if message is not None else None


def _start_assistant_turn(session: ChatSession, user_message: ChatMessage, request: SendChatMessageRequest):
    user_turn_id = request.user_turn_id or f"user-turn:{uuid.uuid4().hex}"
    record = default_assistant_turn_coordinator().start(
        session_id=session.id,
        user_message_id=user_message.id,
        user_turn_id=user_turn_id,
        speech_segment_id=request.speech_segment_id,
    )
    user_message.metadata.update({
        "user_turn_id": record.user_turn_id,
        "speech_segment_id": record.speech_segment_id,
        "assistant_turn_id": record.assistant_turn_id,
        "assistant_turn": record.model_dump(mode="json"),
    })
    return record


def _tag_turn_and_save(store, session: ChatSession, user_message_id: str, assistant_turn_id: str, user_turn_id: str, speech_segment_id: str | None) -> None:
    segment_id = session.active_segment_id
    found_user = False
    coordinator = default_assistant_turn_coordinator()
    for message in session.messages:
        if message.id == user_message_id:
            message.metadata.update({
                "segment_id": segment_id,
                "user_turn_id": user_turn_id,
                "speech_segment_id": speech_segment_id,
                "assistant_turn_id": assistant_turn_id,
            })
            turn = coordinator.get(assistant_turn_id)
            if turn is not None:
                message.metadata["assistant_turn"] = turn.model_dump(mode="json")
            found_user = True
            continue
        if found_user and message.role == "assistant":
            message.metadata.update({"segment_id": segment_id, "assistant_turn_id": assistant_turn_id})
            break
    store._save_sessions(_replace_session(store._load_sessions(), session))


def _persist_interrupted_reply(store, *, session_id: str, user_message_id: str, assistant_turn_id: str, content: str, metadata: dict[str, Any]) -> ChatSession | None:
    sessions = store._load_sessions()
    coordinator = default_assistant_turn_coordinator()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        user_message = next((message for message in session.messages if message.id == user_message_id), None)
        if user_message is None:
            return session
        user_message.metadata["generation_status"] = "interrupted"
        turn = coordinator.get(assistant_turn_id)
        if turn is not None:
            user_message.metadata["assistant_turn"] = turn.model_dump(mode="json")
        already_persisted = any(
            message.role == "assistant" and message.metadata.get("assistant_turn_id") == assistant_turn_id
            for message in session.messages
        )
        generated = content.strip()
        if generated and not already_persisted:
            session.messages.append(ChatMessage(
                id=f"msg:{uuid.uuid4().hex}",
                role="assistant",
                content=generated,
                created_at=_utcnow(),
                metadata={
                    **metadata,
                    "generation_status": "interrupted",
                    "delivery_status": "interrupted",
                    "assistant_turn_id": assistant_turn_id,
                },
            ))
        session.message_count = len(session.messages)
        session.updated_at = _utcnow()
        sessions[index] = session
        store._save_sessions(sessions)
        return session
    return None


def _replace_session(sessions: list[ChatSession], replacement: ChatSession) -> list[ChatSession]:
    return [replacement if session.id == replacement.id else session for session in sessions]
