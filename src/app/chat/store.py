"""Local backend-owned chat session history store."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _provider_key(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return text.split(":", 1)[1] if text.startswith("llm:") else text


def _model_key(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    parts = text.split(":", 2)
    if len(parts) == 3 and parts[0] == "llm":
        return parts[2] or None
    return text


def default_chat_store_path() -> Path:
    override = os.environ.get("OMNIX_CHAT_STORE_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "omnix_chat_sessions.json"


class ChatSessionStore:
    """Small JSON-backed chat history store."""

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
                metadata={"generation_status": "running", "agent_mode": request.agent_mode},
            )
            provider_id = request.provider_id or session.provider_id
            model_id = request.model_id or session.model_id
            answer = self._generate_reply(session, message, provider_id=provider_id, model_id=model_id, request=request)
            assistant_message = ChatMessage(
                id=f"msg:{uuid.uuid4().hex}",
                role="assistant",
                content=answer["content"],
                created_at=_utcnow(),
                metadata=answer["metadata"],
            )
            message.metadata["generation_status"] = "completed"
            session.messages.append(message)
            session.messages.append(assistant_message)
            session.provider_id = provider_id
            session.model_id = model_id
            session.message_count = len(session.messages)
            if session.title.strip().lower() in {"new chat", "new chat..."}:
                session.title = message.content[:48] or "New chat"
            session.updated_at = assistant_message.created_at
            sessions[index] = session
            self._save_sessions(sessions)
            return session, message

        return None

    def _generate_reply(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        provider_id: str | None,
        model_id: str | None,
        request: SendChatMessageRequest,
    ) -> dict[str, Any]:
        if request.agent_mode:
            return self._generate_mode_reply(session, user_message, request=request)
        return self._generate_provider_reply(session, user_message, provider_id=provider_id, model_id=model_id)

    def _generate_mode_reply(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        request: SendChatMessageRequest,
    ) -> dict[str, Any]:
        from app.assist_core.mode_chat import ModeChatRequest, plan_mode_chat

        result = plan_mode_chat(
            ModeChatRequest(
                content=user_message.content,
                session_id=session.id,
                dry_run=request.dry_run,
                metadata={"source": "chat_session_store"},
            )
        )
        payload = result.result
        content = str(payload.get("response") or "Agent mode did not produce a response.").strip()
        return {
            "content": content,
            "metadata": {
                "generation_status": "completed",
                "agent_mode": True,
                "dry_run": request.dry_run,
                "backend": result.backend,
                "mode_result": payload,
                "error": result.error,
            },
        }

    def _generate_provider_reply(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        provider_id: str | None,
        model_id: str | None,
    ) -> dict[str, Any]:
        from app import shared
        from app.providers import ChatMessage as ProviderMessage

        provider_name = _provider_key(provider_id)
        provider = shared.get_provider(provider_name)
        if provider is None:
            raise RuntimeError("Chat provider is not available")

        messages: list[ProviderMessage] = []
        if not any(message.role == "system" for message in session.messages):
            messages.append(ProviderMessage(role="system", content=shared.get_global_system_prompt()))
        for message in session.messages:
            messages.append(ProviderMessage(role=message.role, content=message.content))
        messages.append(ProviderMessage(role="user", content=user_message.content))

        model_name = _model_key(model_id)
        response = provider.chat_completion(messages=messages, model=model_name, stream=False)
        content = (getattr(response, "content", "") or "").strip()
        if not content:
            raise RuntimeError("Chat response was empty")
        metadata: dict[str, Any] = {
            "generation_status": "completed",
            "provider_id": provider_id,
            "model_id": model_id,
            "resolved_model": getattr(response, "model", None) or model_name,
        }
        usage = getattr(response, "usage", None)
        if usage:
            metadata["usage"] = usage
        thinking = getattr(response, "thinking", None) or getattr(response, "reasoning", None)
        if thinking:
            metadata["thinking"] = thinking
        return {"content": content, "metadata": metadata}

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
