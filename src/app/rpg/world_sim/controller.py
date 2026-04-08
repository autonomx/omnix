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

    _MAX_THREADS = 8
    _MAX_CONSEQUENCES = 8
    _MAX_RUMORS = 8
    _MAX_LOCATIONS = 12
    _MAX_HOTSPOTS = 8
    _MAX_EFFECTS = 50

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
    def from_dict(cls, data: dict) -> "WorldSimController":
        ctrl = cls()
        raw = data or {}
        ctrl.state = WorldSimState.from_dict(raw)

        # Defensive normalization for nested models in case older saves or
        # partial payloads contain plain dicts.
        ctrl.state.faction_drift = {
            str(k): (v if isinstance(v, FactionDriftState) else FactionDriftState.from_dict(v))
            for k, v in (ctrl.state.faction_drift or {}).items()
        }
        ctrl.state.rumor_states = {
            str(k): (v if isinstance(v, RumorPropagationState) else RumorPropagationState.from_dict(v))
            for k, v in (ctrl.state.rumor_states or {}).items()
        }
        ctrl.state.location_conditions = {
            str(k): (v if isinstance(v, LocationConditionState) else LocationConditionState.from_dict(v))
            for k, v in (ctrl.state.location_conditions or {}).items()
        }
        ctrl.state.npc_activities = {
            str(k): (v if isinstance(v, NPCActivityState) else NPCActivityState.from_dict(v))
            for k, v in (ctrl.state.npc_activities or {}).items()
        }
        if not isinstance(ctrl.state.world_pressure, WorldPressureState):
            ctrl.state.world_pressure = WorldPressureState.from_dict(ctrl.state.world_pressure or {})
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
        # --- Coherence data ---
        if coherence_core is not None:
            coherence_query = getattr(coherence_core, "query", None)
            locations = (
                coherence_query.get_known_locations()
                if coherence_query is not None and hasattr(coherence_query, "get_known_locations")
                else []
            )
            unresolved_threads = (
                coherence_query.get_unresolved_threads()
                if coherence_query is not None and hasattr(coherence_query, "get_unresolved_threads")
                else []
            )
            recent_consequences = (
                coherence_query.get_recent_consequences(limit=self._MAX_CONSEQUENCES)
                if coherence_query is not None and hasattr(coherence_query, "get_recent_consequences")
                else []
            )
        else:
            locations = []
            unresolved_threads = []
            recent_consequences = []

        # --- Social state data ---
        if social_state_core is not None:
            social_query = getattr(social_state_core, "query", None)
            social_state = getattr(social_state_core, "state", None) or getattr(social_state_core, "get_state", lambda: None)()
            if social_query is not None and hasattr(social_query, "get_known_factions"):
                factions = social_query.get_known_factions(social_state)
            else:
                factions = []
            if social_query is not None and hasattr(social_query, "get_recent_rumors"):
                recent_rumors = social_query.get_recent_rumors(social_state, limit=self._MAX_RUMORS)
            else:
                recent_rumors = []
            if social_query is not None and hasattr(social_query, "get_relationship_hotspots"):
                hotspots = social_query.get_relationship_hotspots(social_state)
            else:
                hotspots = []
        else:
            factions = []
            recent_rumors = []
            hotspots = []

        # Apply fixed caps and deterministic sorting (deduplicate locations)
        locations = sorted(set(str(x) for x in locations if x))[: self._MAX_LOCATIONS]
        factions = sorted(str(x) for x in factions if x)[: self._MAX_LOCATIONS]
        unresolved_threads = self._sorted_dicts(
            unresolved_threads,
            primary_keys=("thread_id", "id", "name"),
            limit=self._MAX_THREADS,
        )
        recent_consequences = self._sorted_dicts(
            recent_consequences,
            primary_keys=("consequence_id", "id", "tick"),
            limit=self._MAX_CONSEQUENCES,
        )
        recent_rumors = self._sorted_dicts(
            recent_rumors,
            primary_keys=("rumor_id", "id", "text"),
            limit=self._MAX_RUMORS,
        )
        hotspots = self._sorted_dicts(
            hotspots,
            primary_keys=("entity_a", "entity_b", "score"),
            limit=self._MAX_HOTSPOTS,
        )

        # --- Arc control guidance ---
        arc_guidance = (
            arc_control_controller.build_world_sim_guidance()
            if arc_control_controller is not None
            and hasattr(arc_control_controller, "build_world_sim_guidance")
            else {}
        )

        # --- Encounter aftermath ---
        encounter_seed = (
            encounter_controller.build_world_sim_seed()
            if encounter_controller is not None
            and hasattr(encounter_controller, "build_world_sim_seed")
            else {}
        )

        return {
            "tick": tick,
            "locations": locations,
            "unresolved_threads": unresolved_threads,
            "recent_consequences": recent_consequences,
            "factions": factions,
            "recent_rumors": recent_rumors,
            "hotspots": hotspots,
            "arc_guidance": arc_guidance,
            "encounter_seed": encounter_seed,
        }

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
        if len(self.state.recent_effects) > self._MAX_EFFECTS:
            overflow = len(self.state.recent_effects) - self._MAX_EFFECTS
            self.state.recent_effects = self.state.recent_effects[overflow:]

    @staticmethod
    def _sorted_dicts(
        items: list[dict] | None,
        primary_keys: tuple[str, ...],
        limit: int,
    ) -> list[dict]:
        """Sort and cap a list of dicts deterministically."""
        rows = [dict(x) for x in (items or []) if isinstance(x, dict)]
        def _key(row: dict) -> tuple:
            vals = []
            for key in primary_keys:
                vals.append(str(row.get(key, "")))
            vals.append(str(sorted(row.items())))
            return tuple(vals)
        rows.sort(key=_key)
        return rows[:limit]

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