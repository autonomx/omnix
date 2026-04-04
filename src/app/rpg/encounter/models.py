"""Phase 8.2 — Encounter Models.

Explicit, deterministic, serializable dataclasses for tactical encounter
state.  These models define the encounter overlay that governs mode-aware
option generation and resolution without replacing the existing scene or
coherence truth layers.

All models support ``to_dict()`` / ``from_dict()`` for snapshot safety.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Union


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SUPPORTED_ENCOUNTER_MODES: frozenset[str] = frozenset({
    "combat",
    "stealth",
    "investigation",
    "diplomacy",
    "chase",
})

SUPPORTED_ENCOUNTER_STATUSES: frozenset[str] = frozenset({
    "inactive",
    "active",
    "resolved",
    "aborted",
})


# ------------------------------------------------------------------
# EncounterParticipant
# ------------------------------------------------------------------

@dataclass
class EncounterParticipant:
    """Encounter-facing participant state (not full world truth)."""

    entity_id: str
    role: str  # player, ally, enemy, neutral, target, bystander
    team: str | None = None
    status: str = "active"  # active, hidden, engaged, downed, escaped, watchful
    position: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "role": self.role,
            "team": self.team,
            "status": self.status,
            "position": self.position,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterParticipant":
        return cls(
            entity_id=data.get("entity_id", ""),
            role=data.get("role", "neutral"),
            team=data.get("team"),
            status=data.get("status", "active"),
            position=data.get("position"),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# EncounterObjective
# ------------------------------------------------------------------

@dataclass
class EncounterObjective:
    """A single encounter-scoped objective."""

    objective_id: str
    kind: str  # defeat, escape, survive, investigate, convince, capture, reach_location
    owner_id: str | None = None
    target_id: str | None = None
    status: str = "active"  # active, progressed, completed, failed, blocked
    progress: Union[int, float] = 0
    required: Union[int, float] = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "objective_id": self.objective_id,
            "kind": self.kind,
            "owner_id": self.owner_id,
            "target_id": self.target_id,
            "status": self.status,
            "progress": self.progress,
            "required": self.required,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterObjective":
        return cls(
            objective_id=data.get("objective_id", ""),
            kind=data.get("kind", ""),
            owner_id=data.get("owner_id"),
            target_id=data.get("target_id"),
            status=data.get("status", "active"),
            progress=data.get("progress", 0),
            required=data.get("required", 1),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# EncounterState
# ------------------------------------------------------------------

@dataclass
class EncounterState:
    """Authoritative encounter-level tactical state."""

    encounter_id: str
    mode: str  # One of SUPPORTED_ENCOUNTER_MODES
    status: str = "active"  # One of SUPPORTED_ENCOUNTER_STATUSES
    round_index: int = 0
    turn_index: int = 0
    scene_location: str | None = None
    participants: list[EncounterParticipant] = field(default_factory=list)
    objectives: list[EncounterObjective] = field(default_factory=list)
    active_entity_id: str | None = None
    pressure: str = "low"  # low, rising, high, critical
    stakes: str = "standard"
    visibility: dict[str, Any] = field(default_factory=dict)
    initiative: list[str] = field(default_factory=list)
    mode_state: dict[str, Any] = field(default_factory=dict)
    resolution_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "encounter_id": self.encounter_id,
            "mode": self.mode,
            "status": self.status,
            "round_index": self.round_index,
            "turn_index": self.turn_index,
            "scene_location": self.scene_location,
            "participants": [p.to_dict() for p in self.participants],
            "objectives": [o.to_dict() for o in self.objectives],
            "active_entity_id": self.active_entity_id,
            "pressure": self.pressure,
            "stakes": self.stakes,
            "visibility": dict(self.visibility),
            "initiative": list(self.initiative),
            "mode_state": dict(self.mode_state),
            "resolution_summary": dict(self.resolution_summary),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterState":
        return cls(
            encounter_id=data.get("encounter_id", ""),
            mode=data.get("mode", "combat"),
            status=data.get("status", "active"),
            round_index=data.get("round_index", 0),
            turn_index=data.get("turn_index", 0),
            scene_location=data.get("scene_location"),
            participants=[
                EncounterParticipant.from_dict(p)
                for p in data.get("participants", [])
            ],
            objectives=[
                EncounterObjective.from_dict(o)
                for o in data.get("objectives", [])
            ],
            active_entity_id=data.get("active_entity_id"),
            pressure=data.get("pressure", "low"),
            stakes=data.get("stakes", "standard"),
            visibility=dict(data.get("visibility", {})),
            initiative=list(data.get("initiative", [])),
            mode_state=dict(data.get("mode_state", {})),
            resolution_summary=dict(data.get("resolution_summary", {})),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# EncounterChoiceContext
# ------------------------------------------------------------------

@dataclass
class EncounterChoiceContext:
    """Context for gameplay control to produce encounter-aware options."""

    encounter_id: str | None = None
    mode: str | None = None
    status: str | None = None
    active_entity_id: str | None = None
    player_role: str = "player"
    available_actions: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    objective_pressure: dict[str, Any] = field(default_factory=dict)
    mode_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "encounter_id": self.encounter_id,
            "mode": self.mode,
            "status": self.status,
            "active_entity_id": self.active_entity_id,
            "player_role": self.player_role,
            "available_actions": list(self.available_actions),
            "constraints": dict(self.constraints),
            "objective_pressure": dict(self.objective_pressure),
            "mode_state": dict(self.mode_state),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterChoiceContext":
        return cls(
            encounter_id=data.get("encounter_id"),
            mode=data.get("mode"),
            status=data.get("status"),
            active_entity_id=data.get("active_entity_id"),
            player_role=data.get("player_role", "player"),
            available_actions=list(data.get("available_actions", [])),
            constraints=dict(data.get("constraints", {})),
            objective_pressure=dict(data.get("objective_pressure", {})),
            mode_state=dict(data.get("mode_state", {})),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# EncounterResolution
# ------------------------------------------------------------------

@dataclass
class EncounterResolution:
    """Structured result of resolving an action within encounter context."""

    encounter_id: str | None = None
    mode: str | None = None
    outcome_type: str = "continue"  # continue, escalate, resolve, abort
    participant_updates: list[dict[str, Any]] = field(default_factory=list)
    objective_updates: list[dict[str, Any]] = field(default_factory=list)
    state_updates: dict[str, Any] = field(default_factory=dict)
    derived_events: list[dict[str, Any]] = field(default_factory=list)
    journal_payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "encounter_id": self.encounter_id,
            "mode": self.mode,
            "outcome_type": self.outcome_type,
            "participant_updates": [dict(u) for u in self.participant_updates],
            "objective_updates": [dict(u) for u in self.objective_updates],
            "state_updates": dict(self.state_updates),
            "derived_events": [dict(e) for e in self.derived_events],
            "journal_payload": dict(self.journal_payload),
            "trace": dict(self.trace),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterResolution":
        return cls(
            encounter_id=data.get("encounter_id"),
            mode=data.get("mode"),
            outcome_type=data.get("outcome_type", "continue"),
            participant_updates=[dict(u) for u in data.get("participant_updates", [])],
            objective_updates=[dict(u) for u in data.get("objective_updates", [])],
            state_updates=dict(data.get("state_updates", {})),
            derived_events=[dict(e) for e in data.get("derived_events", [])],
            journal_payload=dict(data.get("journal_payload", {})),
            trace=dict(data.get("trace", {})),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# EncounterSnapshot (optional dedicated payload)
# ------------------------------------------------------------------

@dataclass
class EncounterSnapshot:
    """Optional snapshot payload for encounter state persistence."""

    active_encounter: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {
            "active_encounter": dict(self.active_encounter) if self.active_encounter else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterSnapshot":
        ae = data.get("active_encounter")
        return cls(active_encounter=dict(ae) if ae else None)
