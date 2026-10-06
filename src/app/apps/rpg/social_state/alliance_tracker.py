"""Phase 7.6 — Alliance Tracker.

Track persistent alliance/hostility drift between entities.
Strength is clamped to [-1.0, 1.0] and status is derived from strength.
"""

from __future__ import annotations

from .models import AllianceRecord, SocialState


class AllianceTracker:
    """Track persistent alliance/hostility drift between entities."""

    def get(
        self, state: SocialState, entity_a: str, entity_b: str
    ) -> AllianceRecord | None:
        """Look up an alliance record."""
        alliance_id = self._alliance_id(entity_a, entity_b)
        return state.alliances.get(alliance_id)

    def upsert(self, state: SocialState, record: AllianceRecord) -> None:
        """Insert or replace an alliance record."""
        state.alliances[record.alliance_id] = record

    def adjust_strength(
        self,
        state: SocialState,
        entity_a: str,
        entity_b: str,
        delta: float,
        event_id: str | None = None,
        metadata: dict | None = None,
    ) -> AllianceRecord:
        """Adjust alliance strength, creating the record if needed.

        Strength is clamped to [-1.0, 1.0]. Status is derived automatically.
        """
        alliance_id = self._alliance_id(entity_a, entity_b)
        record = state.alliances.get(alliance_id)
        if record is None:
            record = AllianceRecord(
                alliance_id=alliance_id,
                entity_a=entity_a,
                entity_b=entity_b,
            )
        record.strength = max(-1.0, min(1.0, record.strength + delta))
        record.status = self._status_from_strength(record.strength)
        if event_id is not None:
            record.last_event_id = event_id
        if metadata:
            record.metadata.update(metadata)
        state.alliances[alliance_id] = record
        return record

    def _alliance_id(self, entity_a: str, entity_b: str) -> str:
        """Generate a deterministic alliance key.

        Uses sorted order so (A, B) and (B, A) map to the same record.
        """
        a, b = sorted([entity_a, entity_b])
        return f"alliance:{a}:{b}"

    def _status_from_strength(self, strength: float) -> str:
        """Derive alliance status from strength value."""
        if strength >= 0.6:
            return "allied"
        if strength >= 0.2:
            return "friendly"
        if strength > -0.2:
            return "neutral"
        if strength > -0.6:
            return "tense"
        return "hostile"
