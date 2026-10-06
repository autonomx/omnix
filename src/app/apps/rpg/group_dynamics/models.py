"""Phase 7.5 — Group Dynamics Models.

Explicit models for multi-actor social interaction results.
These are resolution artifacts — they describe group interaction state,
not truth owners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class InteractionParticipant:
    """A participant in a multi-actor social interaction."""

    npc_id: str
    role: str
    faction_id: Optional[str] = None
    relationship_to_primary: str = "neutral"
    relationship_to_player: str = "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "role": self.role,
            "faction_id": self.faction_id,
            "relationship_to_primary": self.relationship_to_primary,
            "relationship_to_player": self.relationship_to_player,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionParticipant":
        return cls(
            npc_id=data["npc_id"],
            role=data["role"],
            faction_id=data.get("faction_id"),
            relationship_to_primary=data.get("relationship_to_primary", "neutral"),
            relationship_to_player=data.get("relationship_to_player", "neutral"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SecondaryReaction:
    """A secondary reaction from a non-primary participant."""

    npc_id: str
    reaction_type: str
    summary: str
    emitted_event_types: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "reaction_type": self.reaction_type,
            "summary": self.summary,
            "emitted_event_types": list(self.emitted_event_types),
            "modifiers": list(self.modifiers),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SecondaryReaction":
        return cls(
            npc_id=data["npc_id"],
            reaction_type=data["reaction_type"],
            summary=data["summary"],
            emitted_event_types=list(data.get("emitted_event_types", [])),
            modifiers=list(data.get("modifiers", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CrowdStateView:
    """Snapshot of the crowd / social atmosphere in the scene."""

    mood: str = "neutral"
    tension: str = "low"
    support_level: str = "mixed"
    present_npc_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mood": self.mood,
            "tension": self.tension,
            "support_level": self.support_level,
            "present_npc_ids": list(self.present_npc_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrowdStateView":
        return cls(
            mood=data.get("mood", "neutral"),
            tension=data.get("tension", "low"),
            support_level=data.get("support_level", "mixed"),
            present_npc_ids=list(data.get("present_npc_ids", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RumorSeed:
    """A structured rumor seed for future propagation."""

    rumor_id: str
    source_npc_id: Optional[str]
    subject_id: Optional[str]
    rumor_type: str
    summary: str
    location: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rumor_id": self.rumor_id,
            "source_npc_id": self.source_npc_id,
            "subject_id": self.subject_id,
            "rumor_type": self.rumor_type,
            "summary": self.summary,
            "location": self.location,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RumorSeed":
        return cls(
            rumor_id=data["rumor_id"],
            source_npc_id=data.get("source_npc_id"),
            subject_id=data.get("subject_id"),
            rumor_type=data["rumor_type"],
            summary=data["summary"],
            location=data.get("location"),
            metadata=dict(data.get("metadata", {})),
        )
