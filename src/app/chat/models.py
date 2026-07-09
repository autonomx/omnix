"""Shared chat session contract for the web gateway."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assistant_memory import DEFAULT_PROFILE_ID, DEFAULT_WORKSPACE_ID
from app.characters import (
    InteractionMode,
    SharedMemoryAccess,
    TranscriptPolicy,
    character_mode_enabled,
)
from app.jobs import JobRecord
from app.research import ResearchMode


ChatMessageRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    id: str
    role: ChatMessageRole
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageContentPurpose(StrEnum):
    MODEL = "model"
    MEMORY = "memory"
    SUMMARY = "summary"
    SEARCH = "search"
    TRANSCRIPT = "transcript"
    AUDIT = "audit"
    EXPORT = "export"


def project_message_content(message: ChatMessage, purpose: MessageContentPurpose) -> str:
    content = message.content
    if message.role != "assistant" or message.metadata.get("delivery_status") != "interrupted":
        return content
    if purpose in {MessageContentPurpose.AUDIT, MessageContentPurpose.EXPORT}:
        return content
    key = "visual_delivered_text_end" if purpose == MessageContentPurpose.TRANSCRIPT else "context_delivered_text_end"
    end = _bounded_content_end(message.metadata.get(key), len(content))
    projected = content[:end].rstrip()
    if purpose == MessageContentPurpose.TRANSCRIPT:
        return f"{projected}\n\n[Response interrupted]" if projected else "[Response interrupted]"
    return projected


def _bounded_content_end(value: object, maximum: int) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(maximum, parsed))


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
    interaction_mode: InteractionMode = "system"
    character_id: str | None = Field(default=None, max_length=160)
    voice_asset_id: str | None = Field(default=None, max_length=240)
    read_memory: bool = False
    write_memory: bool = False
    shared_memory_access: SharedMemoryAccess = "none"
    transcript_policy: TranscriptPolicy = "persistent"
    active_segment_id: str | None = Field(default=None, max_length=200)
    character_profile_version: int | None = Field(default=None, ge=1)
    effective_identity_hash: str | None = Field(default=None, min_length=64, max_length=64)
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
    """Client selection; trusted identity/profile content is intentionally absent."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    research_mode_override: ResearchMode | None = None
    interaction_mode: InteractionMode = "system"
    character_id: str | None = Field(default=None, max_length=160)
    voice_asset_id: str | None = Field(default=None, max_length=240)
    read_memory: bool = False
    write_memory: bool = False
    shared_memory_access: SharedMemoryAccess = "none"
    transcript_policy: TranscriptPolicy = "persistent"

    @model_validator(mode="after")
    def validate_interaction_selection(self) -> "CreateChatSessionRequest":
        if self.interaction_mode == "system":
            if self.character_id:
                raise ValueError("system mode cannot select a character")
            if self.shared_memory_access != "none":
                raise ValueError("system mode cannot request shared character memory")
            return self
        if not self.character_id:
            raise ValueError("character mode requires character_id")
        if self.system_prompt:
            raise ValueError("character prompts are resolved by the server")
        if not character_mode_enabled():
            raise ValueError("Character Mode is disabled")
        return self


class UpdateChatResearchModeRequest(BaseModel):
    research_mode_override: ResearchMode | None = None


class SendChatMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    provider_id: str | None = None
    model_id: str | None = None
    agent_mode: bool = False
    dry_run: bool = False
    research_mode: ResearchMode | None = None
    user_turn_id: str | None = Field(default=None, min_length=1, max_length=160)
    speech_segment_id: str | None = Field(default=None, min_length=1, max_length=160)


class SendChatMessageResponse(BaseModel):
    session: ChatSession
    user_message: ChatMessage
    job: JobRecord
    generation_status: Literal["queued"] = "queued"
