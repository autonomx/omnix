"""Phase 7.6 — Persistent Social State Models.

Explicit persistent social state models for reputation edges,
relationship metrics, rumor records, and alliance records.
All models are serializable and snapshot-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReputationEdge:
    """A directed reputation edge between two entities."""

    source_id: str
    target_id: str
    score: float = 0.0
    edge_type: str = "reputation"
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "score": self.score,
            "edge_type": self.edge_type,
            "last_event_id": self.last_event_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReputationEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            score=float(data.get("score", 0.0)),
            edge_type=data.get("edge_type", "reputation"),
            last_event_id=data.get("last_event_id"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RelationshipStateRecord:
    """Persistent relationship metrics between two entities."""

    relationship_id: str
    source_id: str
    target_id: str
    trust: float = 0.0
    fear: float = 0.0
    hostility: float = 0.0
    respect: float = 0.0
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "trust": self.trust,
            "fear": self.fear,
            "hostility": self.hostility,
            "respect": self.respect,
            "last_event_id": self.last_event_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelationshipStateRecord":
        return cls(
            relationship_id=data["relationship_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            trust=float(data.get("trust", 0.0)),
            fear=float(data.get("fear", 0.0)),
            hostility=float(data.get("hostility", 0.0)),
            respect=float(data.get("respect", 0.0)),
            last_event_id=data.get("last_event_id"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RumorRecord:
    """A persistent rumor record tracking spread and status."""

    rumor_id: str
    source_npc_id: str | None
    subject_id: str | None
    rumor_type: str
    summary: str
    location: str | None = None
    spread_level: int = 0
    active: bool = True
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rumor_id": self.rumor_id,
            "source_npc_id": self.source_npc_id,
            "subject_id": self.subject_id,
            "rumor_type": self.rumor_type,
            "summary": self.summary,
            "location": self.location,
            "spread_level": self.spread_level,
            "active": self.active,
            "last_event_id": self.last_event_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RumorRecord":
        return cls(
            rumor_id=data["rumor_id"],
            source_npc_id=data.get("source_npc_id"),
            subject_id=data.get("subject_id"),
            rumor_type=data["rumor_type"],
            summary=data["summary"],
            location=data.get("location"),
            spread_level=int(data.get("spread_level", 0)),
            active=bool(data.get("active", True)),
            last_event_id=data.get("last_event_id"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class AllianceRecord:
    """A persistent alliance/hostility record between two entities."""

    alliance_id: str
    entity_a: str
    entity_b: str
    strength: float = 0.0
    status: str = "neutral"
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "alliance_id": self.alliance_id,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "strength": self.strength,
            "status": self.status,
            "last_event_id": self.last_event_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AllianceRecord":
        return cls(
            alliance_id=data["alliance_id"],
            entity_a=data["entity_a"],
            entity_b=data["entity_b"],
            strength=float(data.get("strength", 0.0)),
            status=data.get("status", "neutral"),
            last_event_id=data.get("last_event_id"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SocialState:
    """Top-level persistent social state container."""

    reputation_edges: dict[str, ReputationEdge] = field(default_factory=dict)
    relationships: dict[str, RelationshipStateRecord] = field(default_factory=dict)
    rumors: dict[str, RumorRecord] = field(default_factory=dict)
    alliances: dict[str, AllianceRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "reputation_edges": {
                k: v.to_dict() for k, v in self.reputation_edges.items()
            },
            "relationships": {
                k: v.to_dict() for k, v in self.relationships.items()
            },
            "rumors": {k: v.to_dict() for k, v in self.rumors.items()},
            "alliances": {k: v.to_dict() for k, v in self.alliances.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SocialState":
        return cls(
            reputation_edges={
                k: ReputationEdge.from_dict(v)
                for k, v in data.get("reputation_edges", {}).items()
            },
            relationships={
                k: RelationshipStateRecord.from_dict(v)
                for k, v in data.get("relationships", {}).items()
            },
            rumors={
                k: RumorRecord.from_dict(v)
                for k, v in data.get("rumors", {}).items()
            },
            alliances={
                k: AllianceRecord.from_dict(v)
                for k, v in data.get("alliances", {}).items()
            },
        )
