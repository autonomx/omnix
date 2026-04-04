"""Phase 8.2 — Encounter Presenter.

Creates UI-safe encounter payloads for the UX layer.
Read-only, presentation-only — no state mutation.
"""

from __future__ import annotations

from typing import Any

from .models import EncounterResolution, EncounterState


# Journal-worthy encounter event kinds
_JOURNALABLE_ENCOUNTER_KINDS: frozenset[str] = frozenset({
    "encounter_started",
    "encounter_resolved",
    "objective_completed",
    "objective_failed",
    "combat_turning_point",
    "stealth_exposed",
    "investigation_breakthrough",
    "diplomacy_breakthrough",
    "chase_outcome",
})


class EncounterPresenter:
    """UI-safe presenter for encounter state and resolution."""

    def present_encounter(self, state: EncounterState | None) -> dict:
        """Build a player-safe encounter payload.

        Does not expose internal trace data.
        """
        if state is None:
            return {}

        objective_summaries = []
        for obj in state.objectives:
            objective_summaries.append({
                "objective_id": obj.objective_id,
                "kind": obj.kind,
                "status": obj.status,
                "progress": obj.progress,
                "required": obj.required,
            })

        participant_summaries = []
        for p in state.participants:
            participant_summaries.append({
                "entity_id": p.entity_id,
                "role": p.role,
                "team": p.team,
                "status": p.status,
            })

        available_tags = list(state.mode_state.keys())

        return {
            "encounter_id": state.encounter_id,
            "mode": state.mode,
            "status": state.status,
            "round_index": state.round_index,
            "turn_index": state.turn_index,
            "active_entity_id": state.active_entity_id,
            "pressure": state.pressure,
            "stakes": state.stakes,
            "objectives": objective_summaries,
            "participants": participant_summaries,
            "mode_state_summary": dict(state.mode_state),
            "available_tags": available_tags,
            "metadata": dict(state.metadata),
        }

    def present_encounter_trace(
        self, resolution: EncounterResolution | None
    ) -> dict:
        """Build a debug-safe trace payload (GM-facing, not player-facing)."""
        if resolution is None:
            return {}

        return {
            "mode": resolution.mode,
            "outcome_type": resolution.outcome_type,
            "reasons": resolution.trace.get("reason", ""),
            "participant_updates": [dict(u) for u in resolution.participant_updates],
            "objective_updates": [dict(u) for u in resolution.objective_updates],
            "state_updates": dict(resolution.state_updates),
        }

    def present_journal_payload(
        self,
        resolution: EncounterResolution | None,
        encounter_state: EncounterState | None = None,
    ) -> dict:
        """Convert encounter outcomes into memory-safe journal form.

        Journals only meaningful outcomes — not every tactical move.
        """
        if resolution is None:
            return {}

        jp = resolution.journal_payload
        if not jp or not jp.get("journalable"):
            return {}

        kind = jp.get("kind", "")
        if kind not in _JOURNALABLE_ENCOUNTER_KINDS:
            return {}

        return {
            "encounter_id": jp.get("encounter_id", ""),
            "mode": jp.get("mode", ""),
            "kind": kind,
            "action": jp.get("action", ""),
            "outcome_type": jp.get("outcome_type", ""),
            "summary": f"Encounter {jp.get('outcome_type', 'event')}: {jp.get('action', '')} in {jp.get('mode', '')} mode",
        }
