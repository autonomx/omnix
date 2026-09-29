"""Data contracts shared by chat, research, memory and character features."""
from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AssistantContextItem(BaseModel):
    source_id: Literal["web_search", "desktop_vision", "live_repair"]
    title: str
    content: str
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


InteractionMode = Literal["system", "character"]
SharedMemoryAccess = Literal["none", "read_only"]
TranscriptPolicy = Literal["persistent", "temporary", "none"]
ResearchMode = Literal["disabled", "quick", "deep"]
ChatMessageRole = Literal["system", "user", "assistant"]
DEFAULT_PROFILE_ID = "profile:local"
DEFAULT_WORKSPACE_ID = "workspace:default"


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


class TranscriptReader(Protocol):
    """Read port for features that need persisted conversation state."""

    def get_session(self, session_id: str) -> ChatSession | None: ...

    def list_sessions(self) -> Any: ...


class ChatSessionMutationPort(TranscriptReader, Protocol):
    """Atomic transcript mutation port shared by Chat and memory snapshots."""

    def _load_sessions(self) -> list[ChatSession]: ...

    def _save_sessions(self, sessions: list[ChatSession]) -> None: ...


class PromptMemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_id: str
    content: str
    scope: str
    category: str
    revision: int = Field(ge=1)
    source: Literal[
        "character",
        "system",
        "shared_system",
        "memory_v2",
        "shared_memory_v2",
    ] = "system"


class DeliveryCheckpointRecorder(Protocol):
    """Port for persisting voice delivery checkpoints into the owning chat turn."""

    def __call__(self, details: dict[str, Any]) -> None: ...


def estimate_tokens(text: str) -> int:
    """Conservative, provider-independent estimate for UTF-8 text."""
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)
