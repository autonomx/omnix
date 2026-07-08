"""Typed Character Mode contracts shared by Chat, voice, and memory."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

InteractionMode = Literal["system", "character"]
SharedMemoryAccess = Literal["none", "read_only"]
TranscriptPolicy = Literal["persistent", "temporary", "none"]

SYSTEM_ASSISTANT_ID = "system-assistant"
SYSTEM_ASSISTANT_NAME = "System Assistant"
SYSTEM_ASSISTANT_IDENTITY = (
    "You are the user's configurable System Assistant. Follow the selected assistant "
    "style while remaining clear, accurate, practical, and honest about uncertainty."
)


class CharacterProfileSnapshot(BaseModel):
    """Immutable server-owned character identity used during prompt resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    personality_prompt: str = Field(min_length=1, max_length=12_000)
    default_greeting: str = Field(default="", max_length=2_000)
    default_voice_asset_id: str | None = Field(default=None, max_length=240)
    speech_style: dict[str, Any] = Field(default_factory=dict)
    identity_policy: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    enabled: bool = True


class InteractionSelection(BaseModel):
    """Untrusted client selection before server-side profile resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interaction_mode: InteractionMode = "system"
    character_id: str | None = Field(default=None, max_length=160)
    voice_asset_id: str | None = Field(default=None, max_length=240)
    read_memory: bool = False
    write_memory: bool = False
    shared_memory_access: SharedMemoryAccess = "none"
    transcript_policy: TranscriptPolicy = "persistent"


class ResolvedInteractionContext(BaseModel):
    """Trusted effective interaction identity produced only by the backend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interaction_mode: InteractionMode
    owner_type: Literal["system", "character"]
    owner_id: str
    display_name: str
    character_id: str | None = None
    voice_asset_id: str | None = None
    read_memory: bool = False
    write_memory: bool = False
    shared_memory_access: SharedMemoryAccess = "none"
    transcript_policy: TranscriptPolicy = "persistent"
    character_profile_version: int | None = Field(default=None, ge=1)
    assistant_identity: list[str] = Field(default_factory=list)
    effective_identity_hash: str = Field(min_length=64, max_length=64)
