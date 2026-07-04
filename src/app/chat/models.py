"""Shared chat session contract for the web gateway."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.jobs import JobRecord


ChatMessageRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    id: str
    role: ChatMessageRole
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSessionSummary(BaseModel):
    id: str
    title: str
    provider_id: str | None = None
    model_id: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str


class ChatSession(ChatSessionSummary):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummary]


class DeleteChatSessionResponse(BaseModel):
    ok: bool = True
    session_id: str


class CreateChatSessionRequest(BaseModel):
    title: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None


class SendChatMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    provider_id: str | None = None
    model_id: str | None = None
    agent_mode: bool = False
    dry_run: bool = False


class SendChatMessageResponse(BaseModel):
    session: ChatSession
    user_message: ChatMessage
    job: JobRecord
    generation_status: Literal["queued"] = "queued"
