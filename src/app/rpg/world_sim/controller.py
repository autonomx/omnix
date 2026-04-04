"""Phase 8.3 — World Simulation Controller.

Authoritative owner of explicit world simulation state.  Performs
deterministic tick advancement using pure reducers.  Must never directly
mutate coherence, social state, memory, arc state, or encounter state.

Snapshot-safe from day one — ``serialize_state()`` / ``deserialize_state()``
are required.
"""

from __future__ import annotations

from typing import Any

from .models import (
    FactionDriftState,
    LocationConditionState,
    NPCActivityState,
    RumorPropagationState,
    WorldPressureState,
    WorldSimState,
    WorldSimTickResult,
)
from .reducers import (
    build_world_sim_trace,
    reduce_faction_drift,
    reduce_location_conditions,
    reduce_npc_activities,
    reduce_rumor_propagation,
    reduce_world_pressure,
)


# Maximum number of recent effects stored in state
_MAX_RECENT_EFFECTS = 50


class WorldSimController:
    """Authoritative owner of background world simulation state.

    This controller:
    - owns ``WorldSimState`` exclusively
    - reads other systems only through ``build_seed_context()``
    - never mutates coherence, social, memory, arc, or encounter state
    - emits structured effects/summaries for downstream consumers
    """

    def __init__(self) -> None:
        self.state = WorldSimState()

    # ------------------------------------------------------------------
    # Read-only accessor
    # ------------------------------------------------------------------

    def get_state(self) -> WorldSimState:
        """Return the current simulation state (read-only by convention)."""
        return self.state

    # ------------------------------------------------------------------
    # Serialization (snapshot-safe)
    # ------------------------------------------------------------------

    def serialize_state(self) -> dict:
        """Return a JSON-safe snapshot of all world-sim state."""
        return dict(self.state.to_dict())

    def deserialize_state(self, data: dict) -> None:
        """Restore world-sim state from a serialized snapshot."""
        self.state = WorldSimState.from_dict(data)

    # Aliases for compatibility
    def to_dict(self) -> dict:
        return self.serialize_state()

    @classmethod
    def from_dict(cls, data: dict) -> WorldSimController:
        ctrl = cls()
        ctrl.deserialize_state(data)
        return ctrl

    # ------------------------------------------------------------------
    # Seed context builder
    # ------------------------------------------------------------------

    def build_seed_context(
        self,
        coherence_core: Any,
        social_state_core: Any,
        arc_control_controller: Any,
        campaign_memory_core: Any,
        encounter_controller: Any | None = None,
        tick: int | None = None,
    ) -> dict:
        """Gather read-only source data needed for simulation.

        This is the **one place** world sim reads other systems.
        Returns a plain dict consumed by reducers.
        """
        ctx: dict[str, Any] = {"tick": tick}

        # --- Coherence data ---
        if coherence_core is not None:
            query = getattr(coherence_core, "query", None)
            if query is not None:
                ctx["unresolved_threads"] = query.get_unresolved_threads()
                ctx["recent_consequences"] = query.get_recent_consequences(limit=5)
                ctx["scene_entities"] = query.get_scene_entities()
                scene_summary = query.get_scene_summary()
                ctx["active_scene_location"] = scene_summary.get("location")
                # known locations
                ctx["known_locations"] = self._extract_known_locations(query)
            else:
                ctx["unresolved_threads"] = []
                ctx["recent_consequences"] = []
                ctx["scene_entities"] = []
                ctx["active_scene_location"] = None
                ctx["known_locations"] = []
        else:
            ctx["unresolved_threads"] = []
            ctx["recent_consequences"] = []
            ctx["scene_entities"] = []
            ctx["active_scene_location"] = None
            ctx["known_locations"] = []

        # --- Social state data ---
        if social_state_core is not None:
            query = getattr(social_state_core, "get_query", lambda: None)()
            state = social_state_core.get_state() if hasattr(social_state_core, "get_state") else None
            if query is not None and state is not None:
                ctx["known_factions"] = self._extract_known_factions(state)
                ctx["recent_rumors"] = self._extract_recent_rumors(state)
                ctx["faction_pressure_map"] = self._extract_faction_pressure_map(state)
            else:
                ctx["known_factions"] = []
                ctx["recent_rumors"] = []
                ctx["faction_pressure_map"] = {}
        else:
            ctx["known_factions"] = []
            ctx["recent_rumors"] = []
            ctx["faction_pressure_map"] = {}

        # --- Arc control guidance ---
        if arc_control_controller is not None:
            if hasattr(arc_control_controller, "build_world_sim_guidance"):
                ctx["arc_guidance"] = arc_control_controller.build_world_sim_guidance()
            else:
                ctx["arc_guidance"] = {}
        else:
            ctx["arc_guidance"] = {}

        # --- Encounter aftermath ---
        if encounter_controller is not None:
            if hasattr(encounter_controller, "build_world_sim_seed"):
                ctx["encounter_aftermath"] = encounter_controller.build_world_sim_seed()
            else:
                ctx["encounter_aftermath"] = {}
        else:
            ctx["encounter_aftermath"] = {}

        return ctx

    # ------------------------------------------------------------------
    # Advance
    # ------------------------------------------------------------------

    def advance(
        self,
        coherence_core: Any,
        social_state_core: Any,
        arc_control_controller: Any,
        campaign_memory_core: Any,
        encounter_controller: Any | None = None,
        tick: int | None = None,
    ) -> WorldSimTickResult:
        """Primary entry point: advance the background simulation by one step.

        1. Build seed context (reads other systems)
        2. Run deterministic reducers
        3. Update world-sim-owned state only
        4. Emit structured effect payloads
        5. Store last result

        Returns:
            WorldSimTickResult with all generated effects and summaries.
        """
        seed_ctx = self.build_seed_context(
            coherence_core=coherence_core,
            social_state_core=social_state_core,
            arc_control_controller=arc_control_controller,
            campaign_memory_core=campaign_memory_core,
            encounter_controller=encounter_controller,
            tick=tick,
        )

        # Pass current state to reducers as dicts
        current_faction = {
            k: v.to_dict() for k, v in self.state.faction_drift.items()
        }
        current_rumor = {
            k: v.to_dict() for k, v in self.state.rumor_states.items()
        }
        current_location = {
            k: v.to_dict() for k, v in self.state.location_conditions.items()
        }
        current_npc = {
            k: v.to_dict() for k, v in self.state.npc_activities.items()
        }

        # Run reducers
        new_faction, faction_effects = reduce_faction_drift(current_faction, seed_ctx)
        new_rumor, rumor_effects = reduce_rumor_propagation(current_rumor, seed_ctx)
        new_location, location_effects = reduce_location_conditions(
            current_location, seed_ctx
        )

        # Build location pressure for NPC reducer
        location_pressure: dict[str, str] = {}
        for lid, lstate in new_location.items():
            location_pressure[lid] = lstate.get("pressure", "low")
        seed_ctx["location_pressure"] = location_pressure

        new_npc, npc_effects = reduce_npc_activities(current_npc, seed_ctx)

        # Update seed context for pressure reducer with current outputs
        seed_ctx["faction_drift_current"] = new_faction
        seed_ctx["location_conditions_current"] = new_location

        new_pressure, pressure_effects = reduce_world_pressure(
            self.state.world_pressure, seed_ctx
        )

        # Build trace
        trace = build_world_sim_trace(
            seed_ctx, faction_effects, rumor_effects,
            location_effects, npc_effects, pressure_effects,
            tick=tick,
        )

        # Collect all effects
        all_effects: list[dict] = (
            faction_effects + rumor_effects + location_effects
            + npc_effects + pressure_effects
        )

        # Build journal payloads from journalable effects
        journal_payloads: list[dict] = [
            e for e in all_effects if e.get("journalable", False)
        ]

        # Build summaries
        summaries: list[dict] = []
        if all_effects:
            summaries.append({
                "summary_type": "world_sim_tick",
                "tick": tick,
                "effect_count": len(all_effects),
                "faction_shifts": len(faction_effects),
                "rumor_changes": len(rumor_effects),
                "location_changes": len(location_effects),
                "npc_changes": len(npc_effects),
                "pressure_changes": len(pressure_effects),
            })

        # --- Update world-sim-owned state ---
        self.state.sim_tick = tick if tick is not None else self.state.sim_tick + 1
        self.state.status = "active"

        self.state.faction_drift = {
            k: FactionDriftState.from_dict(v) for k, v in new_faction.items()
        }
        self.state.rumor_states = {
            k: RumorPropagationState.from_dict(v) for k, v in new_rumor.items()
        }
        self.state.location_conditions = {
            k: LocationConditionState.from_dict(v) for k, v in new_location.items()
        }
        self.state.npc_activities = {
            k: NPCActivityState.from_dict(v) for k, v in new_npc.items()
        }
        self.state.world_pressure = new_pressure

        # Append and trim recent effects
        self.state.recent_effects.extend(all_effects)
        self._trim_recent_effects()

        # Build result
        result = WorldSimTickResult(
            tick=tick,
            advanced=True,
            generated_effects=all_effects,
            generated_summaries=summaries,
            journal_payloads=journal_payloads,
            trace=trace,
            metadata={},
        )

        self.state.last_result = result.to_dict()
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trim_recent_effects(self) -> None:
        """Deterministically trim recent effects to bounded size."""
        if len(self.state.recent_effects) > _MAX_RECENT_EFFECTS:
            overflow = len(self.state.recent_effects) - _MAX_RECENT_EFFECTS
            self.state.recent_effects = self.state.recent_effects[overflow:]

    @staticmethod
    def _extract_known_locations(query: Any) -> list[str]:
        """Extract known location IDs from coherence query."""
        locations: list[str] = []
        if hasattr(query, "get_known_locations"):
            return sorted(query.get_known_locations())
        # Fallback: try to derive from scene summary
        scene = query.get_scene_summary() if hasattr(query, "get_scene_summary") else {}
        loc = scene.get("location")
        if loc:
            locations.append(loc)
        return sorted(set(locations))

    @staticmethod
    def _extract_known_factions(state: Any) -> list[str]:
        """Extract known faction IDs from social state."""
        factions: set[str] = set()
        # Try alliances
        if hasattr(state, "alliances"):
            for alliance in state.alliances.values():
                for eid in (
                    getattr(alliance, "entity_a", None),
                    getattr(alliance, "entity_b", None),
                ):
                    if eid:
                        factions.add(eid)
        return sorted(factions)

    @staticmethod
    def _extract_recent_rumors(state: Any) -> list[dict]:
        """Extract recent active rumors from social state."""
        rumors: list[dict] = []
        if hasattr(state, "rumors"):
            for rumor in state.rumors.values():
                if getattr(rumor, "active", False):
                    rumors.append(rumor.to_dict())
        return rumors[:5]

    @staticmethod
    def _extract_faction_pressure_map(state: Any) -> dict[str, str]:
        """Derive faction pressure from social state."""
        pressure: dict[str, str] = {}
        # Simple derivation: factions with hostile relationships have higher pressure
        if hasattr(state, "relationships"):
            for rel in state.relationships.values():
                status = getattr(rel, "status", "")
                entity_a = getattr(rel, "source_id", "")
                if status in ("hostile", "enemy") and entity_a:
                    pressure[entity_a] = "high"
        return pressure
