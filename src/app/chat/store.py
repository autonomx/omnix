"""Local backend-owned chat session history store."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.runtime_paths import resources_data_root

from .models import (
    ChatMessage,
    ChatSession,
    ChatSessionListResponse,
    ChatSessionSummary,
    CreateChatSessionRequest,
    SendChatMessageRequest,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_chat_store_path() -> Path:
    override = os.environ.get("OMNIX_CHAT_STORE_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "omnix_chat_sessions.json"


class ChatSessionStore:
    """Small JSON-backed chat history store.

    The store owns conversation history only. It does not invoke providers;
    generation is represented as shared jobs so worker routing can attach later.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_chat_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_sessions(self) -> ChatSessionListResponse:
        sessions = [self._summary(session) for session in self._load_sessions()]
        sessions.sort(key=lambda session: session.updated_at, reverse=True)
        return ChatSessionListResponse(sessions=sessions)

    def create_session(self, request: CreateChatSessionRequest) -> ChatSession:
        now = _utcnow()
        title = (request.title or "New chat").strip() or "New chat"
        messages: list[ChatMessage] = []
        if request.system_prompt:
            messages.append(
                ChatMessage(
                    id=f"msg:{uuid.uuid4().hex}",
                    role="system",
                    content=request.system_prompt,
                    created_at=now,
                    metadata={"source": "chat_session_request"},
                )
            )

        session = ChatSession(
            id=f"chat:{uuid.uuid4().hex}",
            title=title,
            provider_id=request.provider_id,
            model_id=request.model_id,
            message_count=len(messages),
            messages=messages,
            created_at=now,
            updated_at=now,
        )
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        for session in self._load_sessions():
            if session.id == session_id:
                return session
        return None

    def append_user_message(self, session_id: str, request: SendChatMessageRequest) -> tuple[ChatSession, ChatMessage] | None:
        sessions = self._load_sessions()
        now = _utcnow()
        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue

            message = ChatMessage(
                id=f"msg:{uuid.uuid4().hex}",
                role="user",
                content=request.content.strip(),
                created_at=now,
                metadata={"generation_status": "queued"},
            )
            session.messages.append(message)
            session.provider_id = request.provider_id or session.provider_id
            session.model_id = request.model_id or session.model_id
            session.message_count = len(session.messages)
            session.updated_at = now
            sessions[index] = session
            self._save_sessions(sessions)
            return session, message

        return None

    def _load_sessions(self) -> list[ChatSession]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [ChatSession.model_validate(session) for session in payload.get("sessions", [])]

    def _save_sessions(self, sessions: list[ChatSession]) -> None:
        payload = {"sessions": [session.model_dump(mode="json") for session in sessions]}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _summary(session: ChatSession) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=session.id,
            title=session.title,
            provider_id=session.provider_id,
            model_id=session.model_id,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


def default_chat_store() -> ChatSessionStore:
    return ChatSessionStore()
