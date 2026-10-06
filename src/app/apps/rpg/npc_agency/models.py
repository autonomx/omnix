"""Phase 7.4 — NPC Agency Models.

Structured models for NPC interaction evaluation and outcomes.
These are resolution artifacts — they describe NPC decision state,
not truth owners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NPCRelationshipView:
    """Snapshot of an NPC's relationship toward a target."""

    npc_id: str
    target_id: Optional[str] = None
    trust: float = 0.0
    fear: float = 0.0
    hostility: float = 0.0
    respect: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "target_id": self.target_id,
            "trust": self.trust,
            "fear": self.fear,
            "hostility": self.hostility,
            "respect": self.respect,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCRelationshipView":
        return cls(
            npc_id=data["npc_id"],
            target_id=data.get("target_id"),
            trust=float(data.get("trust", 0.0)),
            fear=float(data.get("fear", 0.0)),
            hostility=float(data.get("hostility", 0.0)),
            respect=float(data.get("respect", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class FactionAlignmentView:
    """Snapshot of an NPC's faction alignment."""

    npc_id: str
    faction_id: Optional[str] = None
    alignment: str = "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "faction_id": self.faction_id,
            "alignment": self.alignment,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FactionAlignmentView":
        return cls(
            npc_id=data["npc_id"],
            faction_id=data.get("faction_id"),
            alignment=data.get("alignment", "neutral"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class NPCDecisionContext:
    """Full context assembled for an NPC decision."""

    npc_id: str
    intent_type: str
    target_id: Optional[str] = None
    scene_summary: dict[str, Any] = field(default_factory=dict)
    known_facts: dict[str, Any] = field(default_factory=dict)
    commitments: list[dict] = field(default_factory=list)
    recent_consequences: list[dict] = field(default_factory=list)
    relationship: Optional[NPCRelationshipView] = None
    faction_alignment: Optional[FactionAlignmentView] = None
    pacing: dict[str, Any] = field(default_factory=dict)
    gm_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "intent_type": self.intent_type,
            "target_id": self.target_id,
            "scene_summary": dict(self.scene_summary),
            "known_facts": dict(self.known_facts),
            "commitments": list(self.commitments),
            "recent_consequences": list(self.recent_consequences),
            "relationship": self.relationship.to_dict() if self.relationship else None,
            "faction_alignment": (
                self.faction_alignment.to_dict() if self.faction_alignment else None
            ),
            "pacing": dict(self.pacing),
            "gm_context": dict(self.gm_context),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCDecisionContext":
        rel_data = data.get("relationship")
        fac_data = data.get("faction_alignment")
        return cls(
            npc_id=data["npc_id"],
            intent_type=data["intent_type"],
            target_id=data.get("target_id"),
            scene_summary=dict(data.get("scene_summary", {})),
            known_facts=dict(data.get("known_facts", {})),
            commitments=list(data.get("commitments", [])),
            recent_consequences=list(data.get("recent_consequences", [])),
            relationship=(
                NPCRelationshipView.from_dict(rel_data) if rel_data else None
            ),
            faction_alignment=(
                FactionAlignmentView.from_dict(fac_data) if fac_data else None
            ),
            pacing=dict(data.get("pacing", {})),
            gm_context=dict(data.get("gm_context", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class NPCDecisionResult:
    """Outcome of an NPC decision policy evaluation."""

    npc_id: str
    outcome: str
    response_type: str
    summary: str
    emitted_event_types: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "outcome": self.outcome,
            "response_type": self.response_type,
            "summary": self.summary,
            "emitted_event_types": list(self.emitted_event_types),
            "modifiers": list(self.modifiers),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCDecisionResult":
        return cls(
            npc_id=data["npc_id"],
            outcome=data["outcome"],
            response_type=data["response_type"],
            summary=data["summary"],
            emitted_event_types=list(data.get("emitted_event_types", [])),
            modifiers=list(data.get("modifiers", [])),
            metadata=dict(data.get("metadata", {})),
        )
