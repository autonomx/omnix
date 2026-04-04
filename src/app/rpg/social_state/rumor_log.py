"""Phase 7.6 — Rumor Log.

Persist rumors created from seeds and track structured spread progression.
No probabilistic spread yet — just structured progression.
"""

from __future__ import annotations

from .models import RumorRecord, SocialState


class RumorLog:
    """Persist and manage rumor records."""

    def get(self, state: SocialState, rumor_id: str) -> RumorRecord | None:
        """Look up a rumor record by ID."""
        return state.rumors.get(rumor_id)

    def upsert(self, state: SocialState, rumor: RumorRecord) -> None:
        """Insert or replace a rumor record."""
        state.rumors[rumor.rumor_id] = rumor

    def seed_rumor(
        self,
        state: SocialState,
        rumor_id: str,
        source_npc_id: str | None,
        subject_id: str | None,
        rumor_type: str,
        summary: str,
        location: str | None,
        event_id: str | None = None,
        metadata: dict | None = None,
    ) -> RumorRecord:
        """Create a new rumor from a seed event."""
        rumor = RumorRecord(
            rumor_id=rumor_id,
            source_npc_id=source_npc_id,
            subject_id=subject_id,
            rumor_type=rumor_type,
            summary=summary,
            location=location,
            spread_level=0,
            active=True,
            last_event_id=event_id,
            metadata=dict(metadata) if metadata else {},
        )
        state.rumors[rumor_id] = rumor
        return rumor

    def increase_spread(
        self,
        state: SocialState,
        rumor_id: str,
        amount: int = 1,
        event_id: str | None = None,
    ) -> RumorRecord | None:
        """Increase the spread level of an existing rumor."""
        rumor = state.rumors.get(rumor_id)
        if rumor is None:
            return None
        rumor.spread_level += amount
        if event_id is not None:
            rumor.last_event_id = event_id
        return rumor

    def deactivate(
        self,
        state: SocialState,
        rumor_id: str,
        event_id: str | None = None,
    ) -> RumorRecord | None:
        """Deactivate a rumor."""
        rumor = state.rumors.get(rumor_id)
        if rumor is None:
            return None
        rumor.active = False
        if event_id is not None:
            rumor.last_event_id = event_id
        return rumor
