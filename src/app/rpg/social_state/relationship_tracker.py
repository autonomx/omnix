"""Phase 7.6 — Relationship Tracker.

Manage persistent trust/fear/hostility/respect records.
All metrics are clamped to [-1.0, 1.0].
"""

from __future__ import annotations

from .models import RelationshipStateRecord, SocialState


class RelationshipTracker:
    """Manage persistent relationship state records."""

    def get(
        self, state: SocialState, source_id: str, target_id: str
    ) -> RelationshipStateRecord | None:
        """Look up a relationship record."""
        rel_id = self._relationship_id(source_id, target_id)
        return state.relationships.get(rel_id)

    def upsert(self, state: SocialState, record: RelationshipStateRecord) -> None:
        """Insert or replace a relationship record."""
        state.relationships[record.relationship_id] = record

    def adjust(
        self,
        state: SocialState,
        source_id: str,
        target_id: str,
        trust: float = 0.0,
        fear: float = 0.0,
        hostility: float = 0.0,
        respect: float = 0.0,
        event_id: str | None = None,
        metadata: dict | None = None,
    ) -> RelationshipStateRecord:
        """Adjust relationship metrics, creating the record if needed.

        All metrics are clamped to [-1.0, 1.0].
        """
        rel_id = self._relationship_id(source_id, target_id)
        record = state.relationships.get(rel_id)
        if record is None:
            record = RelationshipStateRecord(
                relationship_id=rel_id,
                source_id=source_id,
                target_id=target_id,
            )
        record.trust = max(-1.0, min(1.0, record.trust + trust))
        record.fear = max(-1.0, min(1.0, record.fear + fear))
        record.hostility = max(-1.0, min(1.0, record.hostility + hostility))
        record.respect = max(-1.0, min(1.0, record.respect + respect))
        if event_id is not None:
            record.last_event_id = event_id
        if metadata:
            record.metadata.update(metadata)
        state.relationships[rel_id] = record
        return record

    def _relationship_id(self, source_id: str, target_id: str) -> str:
        """Generate a deterministic relationship key."""
        return f"rel:{source_id}:{target_id}"
