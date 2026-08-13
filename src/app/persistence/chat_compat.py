from __future__ import annotations

import json
from typing import Any

from app.chat.models import ChatMessage, ChatSession
from app.chat.retention_policy import transcript_retention_allowed

from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PostgresChatRepositoryAdapter:
    """Compatibility implementation for the current ChatStore contract.

    The public ChatStore can continue to operate while PostgreSQL remains the
    sole authority. Message history is append-only; an attempted transcript
    rewrite is rejected rather than implemented as delete/reinsert persistence.
    """

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def load_sessions(self) -> list[ChatSession]:
        sessions: list[ChatSession] = []
        with unit_of_work(self.database) as work:
            records = work.chats.list_sessions(self.context, limit=200)
            for record in records:
                messages = work.chats.list_messages(
                    self.context,
                    record["id"],
                    limit=500,
                    after_position=-1,
                )
                sessions.append(self._to_session(record, messages))
            work.rollback()
        return sessions

    def save_sessions(self, sessions: list[ChatSession]) -> None:
        with unit_of_work(self.database) as work:
            existing_records = work.chats.list_sessions(self.context, limit=500)
            existing_by_id = {record["id"]: record for record in existing_records}
            requested_ids = {session.id for session in sessions}

            for existing_id in sorted(set(existing_by_id) - requested_ids):
                work.connection.execute(
                    """
                    UPDATE omnix_chat_sessions
                       SET status = 'deleted', revision = revision + 1,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND id = %s AND status = 'active'
                    """,
                    (self.context.workspace_id, existing_id),
                )

            for session in sessions:
                existing = existing_by_id.get(session.id)
                if existing is None:
                    work.chats.create_session(
                        self.context,
                        self._session_payload(session),
                    )
                    stored_messages: list[dict[str, Any]] = []
                else:
                    work.connection.execute(
                        """
                        UPDATE omnix_chat_sessions SET
                            title = %s,
                            provider_id = %s,
                            model_id = %s,
                            project_id = %s,
                            profile_id = %s,
                            interaction_mode = %s,
                            character_id = %s,
                            character_version = %s,
                            memory_enabled = %s,
                            memory_snapshot_id = %s,
                            settings = %s::jsonb,
                            transcript_policy = %s,
                            active_segment_id = %s,
                            status = 'active',
                            revision = revision + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s
                        """,
                        (
                            session.title,
                            session.provider_id,
                            session.model_id,
                            session.project_id,
                            session.profile_id,
                            session.interaction_mode,
                            session.character_id,
                            session.character_profile_version,
                            session.memory_enabled,
                            session.memory_snapshot_id,
                            _json(self._settings(session)),
                            session.transcript_policy,
                            session.active_segment_id,
                            self.context.workspace_id,
                            session.id,
                        ),
                    )
                    stored_messages = work.chats.list_messages(
                        self.context,
                        session.id,
                        limit=500,
                        after_position=-1,
                    )

                stored_ids = [message["id"] for message in stored_messages]
                requested_prefix = [message.id for message in session.messages[: len(stored_ids)]]
                if stored_ids != requested_prefix:
                    raise RuntimeError(
                        f"Chat transcript rewrite rejected for {session.id}; "
                        "PostgreSQL message history is append-only"
                    )
                retained_messages = (
                    session.messages
                    if transcript_retention_allowed(session)
                    else session.messages[: len(stored_ids)]
                )
                for message in retained_messages[len(stored_ids) :]:
                    work.chats.append_message(
                        self.context,
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

    def update_delivery_metadata(
        self,
        *,
        session_id: str,
        assistant_turn_id: str,
        metadata: dict[str, object],
    ) -> bool:
        """Patch delivery metadata without serializing the entire chat workspace."""
        if not metadata:
            return False
        with unit_of_work(self.database) as work:
            cursor = work.connection.execute(
                """
                UPDATE omnix_chat_messages
                   SET metadata = metadata || %s::jsonb
                 WHERE workspace_id = %s
                   AND session_id = %s
                   AND metadata ->> 'assistant_turn_id' = %s
                """,
                (
                    _json(metadata),
                    self.context.workspace_id,
                    session_id,
                    assistant_turn_id,
                ),
            )
            changed = cursor.rowcount > 0
            work.commit()
        return changed

    def _session_payload(self, session: ChatSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "title": session.title,
            "provider_id": session.provider_id,
            "model_id": session.model_id,
            "project_id": session.project_id,
            "profile_id": session.profile_id,
            "interaction_mode": session.interaction_mode,
            "character_id": session.character_id,
            "character_version": session.character_profile_version,
            "memory_enabled": session.memory_enabled,
            "memory_snapshot_id": session.memory_snapshot_id,
            "settings": self._settings(session),
            "transcript_policy": session.transcript_policy,
            "active_segment_id": session.active_segment_id,
        }

    @staticmethod
    def _settings(session: ChatSession) -> dict[str, Any]:
        return {
            "research_mode_override": session.research_mode_override,
            "memory_snapshot_revision": session.memory_snapshot_revision,
            "memory_record_count": session.memory_record_count,
            "memory_last_refreshed_at": session.memory_last_refreshed_at,
            "voice_asset_id": session.voice_asset_id,
            "read_memory": session.read_memory,
            "write_memory": session.write_memory,
            "shared_memory_access": session.shared_memory_access,
            "effective_identity_hash": session.effective_identity_hash,
        }

    @staticmethod
    def _to_session(
        record: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> ChatSession:
        settings = dict(record.get("settings") or {})
        return ChatSession(
            id=record["id"],
            title=record["title"],
            provider_id=record.get("provider_id"),
            model_id=record.get("model_id"),
            research_mode_override=settings.get("research_mode_override"),
            profile_id=record.get("profile_id") or "profile:default",
            workspace_id=record["workspace_id"],
            project_id=record.get("project_id"),
            memory_enabled=bool(record.get("memory_enabled")),
            memory_snapshot_id=record.get("memory_snapshot_id"),
            memory_snapshot_revision=settings.get("memory_snapshot_revision"),
            memory_record_count=int(settings.get("memory_record_count") or 0),
            memory_last_refreshed_at=settings.get("memory_last_refreshed_at"),
            interaction_mode=record.get("interaction_mode") or "system",
            character_id=record.get("character_id"),
            voice_asset_id=settings.get("voice_asset_id"),
            read_memory=bool(settings.get("read_memory")),
            write_memory=bool(settings.get("write_memory")),
            shared_memory_access=settings.get("shared_memory_access") or "none",
            transcript_policy=record.get("transcript_policy") or "persistent",
            active_segment_id=record.get("active_segment_id"),
            character_profile_version=record.get("character_version"),
            effective_identity_hash=settings.get("effective_identity_hash"),
            message_count=len(messages),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            messages=[
                ChatMessage(
                    id=message["id"],
                    role=message["role"],
                    content=message["content"],
                    created_at=message["created_at"],
                    metadata=dict(message.get("metadata") or {}),
                )
                for message in messages
            ],
        )
