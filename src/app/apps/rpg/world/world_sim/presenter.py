"""Phase 8.3 — World Simulation Presenter.

UI-safe surface for world simulation state and recent offscreen
developments.  Returns compact, player-friendly summaries only —
does not expose full reducer internals.
"""

from __future__ import annotations

from typing import Any

from .models import WorldSimState


class WorldSimPresenter:
    """Present world simulation state for UI consumption."""

    def present_state(self, state: WorldSimState | None) -> dict:
        """Return a compact world-state summary for UX payloads.

        Keys:
        - sim_tick
        - status
        - pressure_summary
        - recent_developments (count)
        - notable_locations (list of location condition summaries)
        - notable_factions (list of faction momentum summaries)
        - rumor_heat (count of active/warm rumors)
        - metadata
        """
        if state is None:
            return {
                "sim_tick": 0,
                "status": "idle",
                "pressure_summary": {},
                "recent_developments": 0,
                "notable_locations": [],
                "notable_factions": [],
                "rumor_heat": 0,
                "metadata": {},
            }

        # Pressure summary
        pressure_summary: dict[str, Any] = {
            "active_threads": len(state.world_pressure.active_threads),
            "thread_pressure_count": len(state.world_pressure.pressure_by_thread),
            "location_pressure_count": len(state.world_pressure.pressure_by_location),
            "faction_pressure_count": len(state.world_pressure.pressure_by_faction),
        }

        # Notable locations (those with non-empty conditions)
        notable_locations: list[dict] = []
        for loc_id in sorted(state.location_conditions.keys()):
            loc = state.location_conditions[loc_id]
            if loc.conditions:
                notable_locations.append({
                    "location_id": loc.location_id,
                    "conditions": list(loc.conditions),
                    "pressure": loc.pressure,
                })

        # Notable factions (those not at steady/low)
        notable_factions: list[dict] = []
        for fid in sorted(state.faction_drift.keys()):
            faction = state.faction_drift[fid]
            if faction.momentum != "steady" or faction.pressure != "low":
                notable_factions.append({
                    "faction_id": faction.faction_id,
                    "momentum": faction.momentum,
                    "pressure": faction.pressure,
                })

        # Active rumor count
        rumor_heat = sum(
            1 for r in state.rumor_states.values()
            if r.heat in ("warm", "hot")
        )

        return {
            "sim_tick": state.sim_tick,
            "status": state.status,
            "pressure_summary": pressure_summary,
            "recent_developments": len(state.recent_effects),
            "location_overlays": notable_locations,
            "faction_overlays": notable_factions,
            "rumor_overlays": rumor_heat,
            "metadata": {},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _effect_summary(effect: dict) -> str:
        """Generate a one-line human-readable summary for an effect."""
        etype = effect.get("effect_type", "")
        target = effect.get("target_id", "unknown")
        payload = effect.get("payload", {})

        if etype == "faction_shift":
            return (
                f"Faction '{target}' shifted to "
                f"{payload.get('new_momentum', '?')} momentum, "
                f"{payload.get('new_pressure', '?')} pressure"
            )
        if etype == "rumor_spread":
            return f"Rumor '{target}' spread to {payload.get('spread_to', '?')}"
        if etype == "rumor_cools":
            return f"Rumor '{target}' has cooled"
        if etype == "location_condition_changed":
            return (
                f"Location '{target}' conditions changed to "
                f"{payload.get('new_conditions', [])}"
            )
        if etype == "npc_activity_changed":
            return (
                f"NPC '{target}' now {payload.get('new_activity', '?')}"
            )
        if etype == "thread_pressure_changed":
            return f"World pressure shifted ({payload.get('thread_count', 0)} threads)"
        return f"{etype} affecting {target}"
