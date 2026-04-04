"""Phase 8.3 — World Simulation Presenter.

UI-safe surface for world simulation state and recent offscreen
developments.  Returns compact, player-friendly summaries only —
does not expose full reducer internals.
"""

from __future__ import annotations

from typing import Any

from .models import WorldSimState, WorldSimTickResult


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
            "notable_locations": notable_locations,
            "notable_factions": notable_factions,
            "rumor_heat": rumor_heat,
            "metadata": {},
        }

    def present_recent_effects(
        self, state: WorldSimState | None
    ) -> list[dict]:
        """Return player/GM-safe summaries of recent offscreen developments."""
        if state is None:
            return []

        results: list[dict] = []
        for effect in state.recent_effects:
            results.append({
                "effect_type": effect.get("effect_type", ""),
                "scope": effect.get("scope", ""),
                "target_id": effect.get("target_id"),
                "summary": self._effect_summary(effect),
            })
        return results

    def present_tick_result(
        self, result: WorldSimTickResult | None
    ) -> dict:
        """Present a tick result for action-result UX and debugging."""
        if result is None:
            return {
                "tick": None,
                "advanced": False,
                "effect_count": 0,
                "summary_count": 0,
                "journal_count": 0,
            }

        return {
            "tick": result.tick,
            "advanced": result.advanced,
            "effect_count": len(result.generated_effects),
            "summary_count": len(result.generated_summaries),
            "journal_count": len(result.journal_payloads),
        }

    def present_journal_payloads(
        self, result: WorldSimTickResult | None
    ) -> list[dict]:
        """Return journal-ready payloads from a tick result."""
        if result is None:
            return []
        return [dict(j) for j in result.journal_payloads]

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
