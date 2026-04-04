"""Phase 8.3 — World Simulation Models.

Explicit, serializable simulation artifacts for deterministic background
world simulation.  Every dataclass provides ``to_dict()`` / ``from_dict()``
for snapshot safety.

These models own *background simulation state only* — they must never
contain canonical scene truth, long-term social truth, permanent memory
truth, encounter truth, or raw narrative prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SUPPORTED_WORLD_EFFECT_TYPES: frozenset[str] = frozenset({
    # Faction effects
    "faction_shift",
    "faction_pressure_rise",
    "faction_deescalation",
    # Rumor effects
    "rumor_spread",
    "rumor_cools",
    "rumor_reaches_location",
    # Location effects
    "location_condition_changed",
    "location_tension_rise",
    "location_activity_shift",
    # NPC background effects
    "npc_activity_changed",
    "npc_moves_offscreen",
    "npc_lays_low",
    "npc_searching",
    # Thread / arc pressure effects
    "thread_pressure_changed",
    "background_event_summary",
    # Encounter seeding effects
    "encounter_seeded",
})

SUPPORTED_LOCATION_CONDITIONS: frozenset[str] = frozenset({
    "guarded",
    "tense",
    "crowded",
    "flooded",
    "searched",
    "celebrating",
    "unrest",
    "locked_down",
    "fearful",
    "calm",
})

SUPPORTED_WORLD_SIM_STATUSES: frozenset[str] = frozenset({
    "idle",
    "active",
    "paused",
})


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass
class WorldEffect:
    """A single structured background world effect."""

    effect_id: str
    effect_type: str
    scope: str
    target_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    journalable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "effect_id": self.effect_id,
            "effect_type": self.effect_type,
            "scope": self.scope,
            "target_id": self.target_id,
            "payload": dict(self.payload),
            "journalable": self.journalable,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldEffect:
        return cls(
            effect_id=data.get("effect_id", ""),
            effect_type=data.get("effect_type", ""),
            scope=data.get("scope", ""),
            target_id=data.get("target_id"),
            payload=dict(data.get("payload", {})),
            journalable=bool(data.get("journalable", False)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class FactionDriftState:
    """Background faction momentum / pressure overlay."""

    faction_id: str
    momentum: str = "steady"
    pressure: str = "low"
    stance_overrides: dict[str, str] = field(default_factory=dict)
    active_goals: list[str] = field(default_factory=list)
    recent_changes: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "faction_id": self.faction_id,
            "momentum": self.momentum,
            "pressure": self.pressure,
            "stance_overrides": dict(self.stance_overrides),
            "active_goals": list(self.active_goals),
            "recent_changes": [dict(c) for c in self.recent_changes],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> FactionDriftState:
        return cls(
            faction_id=data.get("faction_id", ""),
            momentum=data.get("momentum", "steady"),
            pressure=data.get("pressure", "low"),
            stance_overrides=dict(data.get("stance_overrides", {})),
            active_goals=list(data.get("active_goals", [])),
            recent_changes=[dict(c) for c in data.get("recent_changes", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RumorPropagationState:
    """Background rumor propagation tracking."""

    rumor_id: str
    source_entity_id: str | None = None
    subject_entity_id: str | None = None
    origin_location: str | None = None
    current_locations: list[str] = field(default_factory=list)
    reach: int = 0
    heat: str = "cold"
    status: str = "dormant"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rumor_id": self.rumor_id,
            "source_entity_id": self.source_entity_id,
            "subject_entity_id": self.subject_entity_id,
            "origin_location": self.origin_location,
            "current_locations": list(self.current_locations),
            "reach": self.reach,
            "heat": self.heat,
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> RumorPropagationState:
        return cls(
            rumor_id=data.get("rumor_id", ""),
            source_entity_id=data.get("source_entity_id"),
            subject_entity_id=data.get("subject_entity_id"),
            origin_location=data.get("origin_location"),
            current_locations=list(data.get("current_locations", [])),
            reach=int(data.get("reach", 0)),
            heat=data.get("heat", "cold"),
            status=data.get("status", "dormant"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class LocationConditionState:
    """Background location condition overlay."""

    location_id: str
    conditions: list[str] = field(default_factory=list)
    pressure: str = "low"
    activity_level: str = "normal"
    active_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "location_id": self.location_id,
            "conditions": list(self.conditions),
            "pressure": self.pressure,
            "activity_level": self.activity_level,
            "active_flags": list(self.active_flags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> LocationConditionState:
        return cls(
            location_id=data.get("location_id", ""),
            conditions=list(data.get("conditions", [])),
            pressure=data.get("pressure", "low"),
            activity_level=data.get("activity_level", "normal"),
            active_flags=list(data.get("active_flags", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class NPCActivityState:
    """Background NPC activity overlay (not full NPC truth)."""

    entity_id: str
    current_location: str | None = None
    activity: str = "idle"
    visibility: str = "unknown"
    status: str = "normal"
    last_update_tick: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "current_location": self.current_location,
            "activity": self.activity,
            "visibility": self.visibility,
            "status": self.status,
            "last_update_tick": self.last_update_tick,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> NPCActivityState:
        return cls(
            entity_id=data.get("entity_id", ""),
            current_location=data.get("current_location"),
            activity=data.get("activity", "idle"),
            visibility=data.get("visibility", "unknown"),
            status=data.get("status", "normal"),
            last_update_tick=data.get("last_update_tick"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorldPressureState:
    """Aggregate world pressure summary."""

    active_threads: list[str] = field(default_factory=list)
    pressure_by_thread: dict[str, str] = field(default_factory=dict)
    pressure_by_location: dict[str, str] = field(default_factory=dict)
    pressure_by_faction: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "active_threads": list(self.active_threads),
            "pressure_by_thread": dict(self.pressure_by_thread),
            "pressure_by_location": dict(self.pressure_by_location),
            "pressure_by_faction": dict(self.pressure_by_faction),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldPressureState:
        return cls(
            active_threads=list(data.get("active_threads", [])),
            pressure_by_thread=dict(data.get("pressure_by_thread", {})),
            pressure_by_location=dict(data.get("pressure_by_location", {})),
            pressure_by_faction=dict(data.get("pressure_by_faction", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorldSimState:
    """Top-level background simulation state."""

    sim_tick: int = 0
    status: str = "idle"
    faction_drift: dict[str, FactionDriftState] = field(default_factory=dict)
    rumor_states: dict[str, RumorPropagationState] = field(default_factory=dict)
    location_conditions: dict[str, LocationConditionState] = field(default_factory=dict)
    npc_activities: dict[str, NPCActivityState] = field(default_factory=dict)
    world_pressure: WorldPressureState = field(default_factory=WorldPressureState)
    recent_effects: list[dict[str, Any]] = field(default_factory=list)
    last_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sim_tick": self.sim_tick,
            "status": self.status,
            "faction_drift": {k: v.to_dict() for k, v in self.faction_drift.items()},
            "rumor_states": {k: v.to_dict() for k, v in self.rumor_states.items()},
            "location_conditions": {
                k: v.to_dict() for k, v in self.location_conditions.items()
            },
            "npc_activities": {k: v.to_dict() for k, v in self.npc_activities.items()},
            "world_pressure": self.world_pressure.to_dict(),
            "recent_effects": [dict(e) for e in self.recent_effects],
            "last_result": dict(self.last_result),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldSimState:
        return cls(
            sim_tick=int(data.get("sim_tick", 0)),
            status=data.get("status", "idle"),
            faction_drift={
                k: FactionDriftState.from_dict(v)
                for k, v in data.get("faction_drift", {}).items()
            },
            rumor_states={
                k: RumorPropagationState.from_dict(v)
                for k, v in data.get("rumor_states", {}).items()
            },
            location_conditions={
                k: LocationConditionState.from_dict(v)
                for k, v in data.get("location_conditions", {}).items()
            },
            npc_activities={
                k: NPCActivityState.from_dict(v)
                for k, v in data.get("npc_activities", {}).items()
            },
            world_pressure=WorldPressureState.from_dict(
                data.get("world_pressure", {})
            ),
            recent_effects=[dict(e) for e in data.get("recent_effects", [])],
            last_result=dict(data.get("last_result", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorldSimTickResult:
    """Top-level result of a single background simulation step."""

    tick: int | None = None
    advanced: bool = False
    generated_effects: list[dict[str, Any]] = field(default_factory=list)
    generated_summaries: list[dict[str, Any]] = field(default_factory=list)
    journal_payloads: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "advanced": self.advanced,
            "generated_effects": [dict(e) for e in self.generated_effects],
            "generated_summaries": [dict(s) for s in self.generated_summaries],
            "journal_payloads": [dict(j) for j in self.journal_payloads],
            "trace": dict(self.trace),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldSimTickResult:
        return cls(
            tick=data.get("tick"),
            advanced=bool(data.get("advanced", False)),
            generated_effects=[dict(e) for e in data.get("generated_effects", [])],
            generated_summaries=[dict(s) for s in data.get("generated_summaries", [])],
            journal_payloads=[dict(j) for j in data.get("journal_payloads", [])],
            trace=dict(data.get("trace", {})),
            metadata=dict(data.get("metadata", {})),
        )
