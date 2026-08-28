"""Shared chat session contract for the web gateway."""
from __future__ import annotations

import re
from enum import Enum
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
_LIVE_VOICE_TURN_ID_PATTERN = re.compile(r"voice-turn:[A-Za-z0-9_.:-]+")

_EXPLICIT_QUICK_RESEARCH = re.compile(
    r"^/(?:search|quick(?:-search)?)(?:\s+)(.+)$",
    re.I | re.S,
)
_EXPLICIT_DEEP_RESEARCH = re.compile(
    r"^/(?:deep(?:-research)?)(?:\s+)(.+)$",
    re.I | re.S,
)
_EXPLICIT_RESEARCH = re.compile(
    r"^/research(?:\s+(quick|deep))?(?:\s+)(.+)$",
    re.I | re.S,
)


def parse_explicit_research_command(content: str) -> tuple[str, ResearchMode] | None:
    """Normalize explicit research slash commands into the existing research lane."""
    text = str(content or "").strip()
    match = _EXPLICIT_QUICK_RESEARCH.match(text)
    if match and match.group(1).strip():
        return match.group(1).strip(), "quick"
    match = _EXPLICIT_DEEP_RESEARCH.match(text)
    if match and match.group(1).strip():
        return match.group(1).strip(), "deep"
    match = _EXPLICIT_RESEARCH.match(text)
    if match and match.group(2).strip():
        mode: ResearchMode = "quick" if str(match.group(1) or "").casefold() == "quick" else "deep"
        return match.group(2).strip(), mode
    return None



class ChatMessage(BaseModel):
    id: str
    role: ChatMessageRole
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageContentPurpose(str, Enum):
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
    metadata = _delivery_metadata(message)
    key = "visual_delivered_text_end" if purpose == MessageContentPurpose.TRANSCRIPT else "context_delivered_text_end"
    end = _bounded_content_end(metadata.get(key), len(content))
    projected = content[:end].rstrip()
    if purpose == MessageContentPurpose.TRANSCRIPT:
        return f"{projected}\n\n[Response interrupted]" if projected else "[Response interrupted]"
    return projected


def _delivery_metadata(message: ChatMessage) -> dict[str, Any]:
    metadata = dict(message.metadata)
    if "context_delivered_text_end" in metadata and "visual_delivered_text_end" in metadata:
        return metadata
    turn_id = str(metadata.get("assistant_turn_id") or "").strip()
    if not turn_id:
        return metadata
    try:
        from .assistant_turns import default_assistant_turn_coordinator

        record = default_assistant_turn_coordinator().get(turn_id)
    except Exception:
        record = None
    if record is not None:
        metadata.setdefault("visual_delivered_text_end", record.visual_delivered_text_end)
        metadata.setdefault("context_delivered_text_end", record.context_delivered_text_end)
    return metadata


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

    @model_validator(mode="before")
    @classmethod
    def apply_central_defaults(cls, value: Any) -> Any:
        from app.platform.effective_defaults import apply_chat_session_defaults

        return apply_chat_session_defaults(value)

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

    @model_validator(mode="before")
    @classmethod
    def normalize_explicit_research_command(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        parsed = parse_explicit_research_command(str(payload.get("content") or ""))
        if parsed is not None:
            content, mode = parsed
            payload["content"] = content
            # A narrow explicit per-turn command outranks any broader persistent
            # Agent setting or caller-supplied research preference.
            payload["research_mode"] = mode
        return payload

    @model_validator(mode="before")
    @classmethod
    def derive_live_voice_ids(cls, value: Any) -> Any:
        """Honor the browser's existing live turn marker without expanding the API."""

        if not isinstance(value, dict):
            return value
        payload = dict(value)
        live_turn_id = str(payload.get("live_voice_turn_id") or "").strip()
        if (
            not live_turn_id
            or len(live_turn_id) > 120
            or _LIVE_VOICE_TURN_ID_PATTERN.fullmatch(live_turn_id) is None
        ):
            return payload
        payload.setdefault("user_turn_id", f"voice-user-turn:{live_turn_id}")
        payload.setdefault("speech_segment_id", f"voice-segment:{live_turn_id}")
        return payload


class SendChatMessageResponse(BaseModel):
    session: ChatSession
    user_message: ChatMessage
    job: JobRecord
    generation_status: Literal["queued"] = "queued"
