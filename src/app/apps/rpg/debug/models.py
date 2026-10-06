"""Phase 8.4 — Debug / Analytics / GM Inspection Models.

Explicit dataclasses for debug payloads.  All models are serializable
and conceptually read-only — the debug layer consumes traces, it does
not create new truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SUPPORTED_DEBUG_NODE_TYPES: frozenset[str] = frozenset({
    "choice_generation",
    "action_resolution",
    "dialogue_planning",
    "encounter_resolution",
    "world_sim_tick",
    "arc_guidance",
    "recovery_event",
    "pack_application",
})

SUPPORTED_DEBUG_SCOPES: frozenset[str] = frozenset({
    "choice",
    "action",
    "dialogue",
    "encounter",
    "world",
    "system",
})


# ------------------------------------------------------------------
# Core trace primitives
# ------------------------------------------------------------------

@dataclass
class DebugTraceNode:
    """A single node in a debug trace — one step or decision point.

    node_id must be deterministic and derived from stable inputs
    (tick, scope, node_type, index, key).  Never use uuid4().
    """

    node_id: str
    node_type: str
    title: str
    summary: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "summary": self.summary,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DebugTraceNode":
        return cls(
            node_id=data.get("node_id", ""),
            node_type=data.get("node_type", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            inputs=dict(data.get("inputs", {})),
            outputs=dict(data.get("outputs", {})),
            reasons=list(data.get("reasons", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DebugTrace:
    """A collection of trace nodes for a single debug scope.

    trace_id must be deterministic and derived from stable inputs
    (tick, scope, key).  Never use uuid4().
    """

    trace_id: str
    tick: int | None = None
    scope: str = "system"
    nodes: list[DebugTraceNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "tick": self.tick,
            "scope": self.scope,
            "nodes": [n.to_dict() for n in self.nodes],
            "warnings": list(self.warnings),
            "contradictions": [dict(c) for c in self.contradictions],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DebugTrace":
        return cls(
            trace_id=data.get("trace_id", ""),
            tick=data.get("tick"),
            scope=data.get("scope", "system"),
            nodes=[
                DebugTraceNode.from_dict(n)
                for n in data.get("nodes", [])
            ],
            warnings=list(data.get("warnings", [])),
            contradictions=[dict(c) for c in data.get("contradictions", [])],
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# Explanation models
# ------------------------------------------------------------------

@dataclass
class ChoiceExplanation:
    """Explains why a particular choice was offered."""

    choice_id: str
    label: str
    source: str
    priority: str
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    related_systems: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "choice_id": self.choice_id,
            "label": self.label,
            "source": self.source,
            "priority": self.priority,
            "reasons": list(self.reasons),
            "constraints": list(self.constraints),
            "related_systems": list(self.related_systems),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChoiceExplanation":
        return cls(
            choice_id=data.get("choice_id", ""),
            label=data.get("label", ""),
            source=data.get("source", ""),
            priority=data.get("priority", ""),
            reasons=list(data.get("reasons", [])),
            constraints=list(data.get("constraints", [])),
            related_systems=list(data.get("related_systems", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class NPCResponseExplanation:
    """Explains why an NPC responded in a particular way."""

    speaker_id: str
    listener_id: str | None = None
    act: str = ""
    tone: str = ""
    stance: str = ""
    drivers: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    blocked_topics: list[str] = field(default_factory=list)
    allowed_topics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "listener_id": self.listener_id,
            "act": self.act,
            "tone": self.tone,
            "stance": self.stance,
            "drivers": dict(self.drivers),
            "reasons": list(self.reasons),
            "blocked_topics": list(self.blocked_topics),
            "allowed_topics": list(self.allowed_topics),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCResponseExplanation":
        return cls(
            speaker_id=data.get("speaker_id", ""),
            listener_id=data.get("listener_id"),
            act=data.get("act", ""),
            tone=data.get("tone", ""),
            stance=data.get("stance", ""),
            drivers=dict(data.get("drivers", {})),
            reasons=list(data.get("reasons", [])),
            blocked_topics=list(data.get("blocked_topics", [])),
            allowed_topics=list(data.get("allowed_topics", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class EncounterExplanation:
    """Explains why an encounter is active and what changed."""

    encounter_id: str | None = None
    mode: str | None = None
    outcome_type: str = ""
    drivers: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    participant_updates: list[dict[str, Any]] = field(default_factory=list)
    objective_updates: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "encounter_id": self.encounter_id,
            "mode": self.mode,
            "outcome_type": self.outcome_type,
            "drivers": dict(self.drivers),
            "reasons": list(self.reasons),
            "participant_updates": [dict(u) for u in self.participant_updates],
            "objective_updates": [dict(u) for u in self.objective_updates],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterExplanation":
        return cls(
            encounter_id=data.get("encounter_id"),
            mode=data.get("mode"),
            outcome_type=data.get("outcome_type", ""),
            drivers=dict(data.get("drivers", {})),
            reasons=list(data.get("reasons", [])),
            participant_updates=[
                dict(u) for u in data.get("participant_updates", [])
            ],
            objective_updates=[
                dict(u) for u in data.get("objective_updates", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorldSimExplanation:
    """Explains a world-sim tick outcome."""

    sim_tick: int = 0
    effects: list[dict[str, Any]] = field(default_factory=list)
    pressure_changes: list[dict[str, Any]] = field(default_factory=list)
    rumor_changes: list[dict[str, Any]] = field(default_factory=list)
    location_changes: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sim_tick": self.sim_tick,
            "effects": [dict(e) for e in self.effects],
            "pressure_changes": [dict(p) for p in self.pressure_changes],
            "rumor_changes": [dict(r) for r in self.rumor_changes],
            "location_changes": [dict(l) for l in self.location_changes],
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldSimExplanation":
        return cls(
            sim_tick=data.get("sim_tick", 0),
            effects=[dict(e) for e in data.get("effects", [])],
            pressure_changes=[dict(p) for p in data.get("pressure_changes", [])],
            rumor_changes=[dict(r) for r in data.get("rumor_changes", [])],
            location_changes=[dict(l) for l in data.get("location_changes", [])],
            reasons=list(data.get("reasons", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class GMInspectionBundle:
    """Full GM-facing debug inspection payload.

    Any bundle identifier stored in metadata must be deterministic
    and derived from stable inputs (tick, choice_id).  Never use uuid4().
    """

    tick: int | None = None
    scene: dict[str, Any] = field(default_factory=dict)
    choice_explanations: list[ChoiceExplanation] = field(default_factory=list)
    dialogue_explanation: dict[str, Any] = field(default_factory=dict)
    encounter_explanation: dict[str, Any] = field(default_factory=dict)
    world_explanation: dict[str, Any] = field(default_factory=dict)
    arc_explanation: dict[str, Any] = field(default_factory=dict)
    recovery_events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "scene": dict(self.scene),
            "choice_explanations": [c.to_dict() for c in self.choice_explanations],
            "dialogue_explanation": dict(self.dialogue_explanation),
            "encounter_explanation": dict(self.encounter_explanation),
            "world_explanation": dict(self.world_explanation),
            "arc_explanation": dict(self.arc_explanation),
            "recovery_events": [dict(r) for r in self.recovery_events],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GMInspectionBundle":
        return cls(
            tick=data.get("tick"),
            scene=dict(data.get("scene", {})),
            choice_explanations=[
                ChoiceExplanation.from_dict(c)
                for c in data.get("choice_explanations", [])
            ],
            dialogue_explanation=dict(data.get("dialogue_explanation", {})),
            encounter_explanation=dict(data.get("encounter_explanation", {})),
            world_explanation=dict(data.get("world_explanation", {})),
            arc_explanation=dict(data.get("arc_explanation", {})),
            recovery_events=[
                dict(r) for r in data.get("recovery_events", [])
            ],
            warnings=list(data.get("warnings", [])),
            metadata=dict(data.get("metadata", {})),
        )
