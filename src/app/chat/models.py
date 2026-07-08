"""Shared chat session contract for the web gateway."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.assistant_memory import DEFAULT_PROFILE_ID, DEFAULT_WORKSPACE_ID
from app.jobs import JobRecord
from app.research import ResearchMode


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
    research_mode_override: ResearchMode | None = None
    profile_id: str = DEFAULT_PROFILE_ID
    workspace_id: str = DEFAULT_WORKSPACE_ID
    project_id: str | None = None
    memory_enabled: bool = False
    memory_snapshot_id: str | None = None
    memory_snapshot_revision: int | None = Field(default=None, ge=1)
    memory_record_count: int = Field(default=0, ge=0)
    memory_last_refreshed_at: str | None = None
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
    """Client-controlled session options; scope identity is intentionally absent."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    research_mode_override: ResearchMode | None = None


class UpdateChatResearchModeRequest(BaseModel):
    research_mode_override: ResearchMode | None = None


class SendChatMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    provider_id: str | None = None
    model_id: str | None = None
    agent_mode: bool = False
    dry_run: bool = False
    research_mode: ResearchMode | None = None


class SendChatMessageResponse(BaseModel):
    session: ChatSession
    user_message: ChatMessage
    job: JobRecord
    generation_status: Literal["queued"] = "queued"
