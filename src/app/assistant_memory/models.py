"""Typed contracts for curated Chat memory and pending candidates."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryScope = Literal["global", "workspace", "project", "session"]
MemoryCategory = Literal["preference", "fact", "project", "relationship", "instruction"]
MemorySource = Literal["user_saved", "assistant_suggested", "imported", "hermes"]
MemoryCandidateStatus = Literal["pending", "rejected", "accepted"]
MemoryRecordStatus = Literal["active", "superseded", "archived"]
MemoryTrustLevel = Literal[
    "user_approved",
    "system_trusted",
    "unverified_import",
    "unverified_agent",
    "external_untrusted",
]
MemorySensitivity = Literal["normal", "sensitive", "secret"]
MemoryProvenanceType = Literal[
    "user_message",
    "assistant_inference",
    "import",
    "hermes",
    "system",
]


class MemoryScopeContext(BaseModel):
    """Backend-resolved identity used for every memory policy decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    project_id: str | None = Field(default=None, max_length=160)
    session_id: str = Field(min_length=1, max_length=200)


class MemoryRecord(BaseModel):
    """Approved or otherwise active curated memory owned by Omnix."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    scope: MemoryScope
    scope_id: str = Field(min_length=1, max_length=200)
    category: MemoryCategory
    source: MemorySource
    content: str = Field(min_length=1, max_length=4096)
    normalized_content: str = Field(min_length=1, max_length=4096)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    pinned: bool = False
    trust_level: MemoryTrustLevel = "user_approved"
    sensitivity: MemorySensitivity = "normal"
    provenance_type: MemoryProvenanceType
    provenance_id: str | None = Field(default=None, max_length=240)
    status: MemoryRecordStatus = "active"
    revision: int = Field(default=1, ge=1)
    created_at: str
    updated_at: str
    expires_at: str | None = None


class MemoryCandidate(BaseModel):
    """Non-prompt-eligible proposal awaiting an explicit resolution."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    source_session_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    candidate_fingerprint: str = Field(min_length=1, max_length=200)
    proposed_scope: MemoryScope
    proposed_scope_id: str = Field(min_length=1, max_length=200)
    proposed_category: MemoryCategory
    proposed_content: str = Field(min_length=1, max_length=4096)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: MemorySource = "assistant_suggested"
    trust_level: MemoryTrustLevel = "unverified_agent"
    sensitivity: MemorySensitivity = "normal"
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)
    status: MemoryCandidateStatus = "pending"
    created_at: str
    resolved_at: str | None = None


class MemorySnapshotItem(BaseModel):
    """Frozen snapshot copy with revocation able to override immutability."""

    model_config = ConfigDict(extra="forbid")

    memory_record_id: str = Field(min_length=1, max_length=200)
    record_revision: int = Field(ge=1)
    frozen_content: str = Field(min_length=1, max_length=4096)
    revoked_at: str | None = None


class MemorySnapshot(BaseModel):
    """Stable per-session memory selection."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    revision: int = Field(default=1, ge=1)
    items: list[MemorySnapshotItem] = Field(default_factory=list)
    token_estimate: int = Field(default=0, ge=0)
    created_at: str
    refreshed_at: str | None = None


class MemoryPolicyDecision(BaseModel):
    """Inspectable result from a pure memory policy check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason: str = Field(min_length=1, max_length=160)
