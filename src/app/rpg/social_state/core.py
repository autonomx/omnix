"""Phase 7.6 — Social State Core.

Central owner for persistent social state, parallel to coherence core.
Fully snapshot-safe and deterministic.
"""

from __future__ import annotations

from typing import Any

from .alliance_tracker import AllianceTracker
from .models import SocialState
from .query import SocialStateQuery
from .reducers import reduce_event
from .relationship_tracker import RelationshipTracker
from .reputation_graph import ReputationGraph
from .rumor_log import RumorLog


class SocialStateCore:
    """Central owner for persistent social state."""

    def __init__(self) -> None:
        self.state = SocialState()
        self.reputation_graph = ReputationGraph()
        self.relationship_tracker = RelationshipTracker()
        self.rumor_log = RumorLog()
        self.alliance_tracker = AllianceTracker()
        self.query = SocialStateQuery()
        self._mode: str = "live"

    def set_mode(self, mode: str) -> None:
        """Set replay/live mode."""
        self._mode = mode

    def get_state(self) -> SocialState:
        """Return the current social state."""
        return self.state

    def get_query(self) -> SocialStateQuery:
        """Return the query API."""
        return self.query

    def apply_event(self, event: Any) -> None:
        """Apply a single event through social state reducers."""
        reduce_event(self, event)

    def apply_events(self, events: list[Any]) -> None:
        """Apply a list of events through social state reducers."""
        for event in events:
            self.apply_event(event)

    def serialize_state(self) -> dict:
        """Serialize the social state for snapshot persistence."""
        return self.state.to_dict()

    def deserialize_state(self, data: dict) -> None:
        """Restore social state from a serialized snapshot."""
        self.state = SocialState.from_dict(data)

    # ------------------------------------------------------------------
    # Phase 7.9 — Pack seed integration
    # ------------------------------------------------------------------

    def load_social_seed(self, payload: dict) -> None:
        """Seed reputation, relationships, rumors, and alliances from a pack.

        Uses the tracker/log APIs rather than raw dict mutation to
        maintain the same invariants as event-driven updates.
        """
        for seed in payload.get("social_seeds", []):
            if not isinstance(seed, dict):
                continue
            seed_type = seed.get("type", "")
            if seed_type == "reputation":
                self.reputation_graph.set_edge(
                    source=seed.get("source", ""),
                    target=seed.get("target", ""),
                    value=seed.get("value", 0),
                    reason=seed.get("reason", "pack_seed"),
                )
            elif seed_type == "relationship":
                self.relationship_tracker.set_relationship(
                    entity_a=seed.get("entity_a", ""),
                    entity_b=seed.get("entity_b", ""),
                    status=seed.get("status", "neutral"),
                    reason=seed.get("reason", "pack_seed"),
                )
            elif seed_type == "rumor":
                self.rumor_log.add_rumor(
                    rumor_id=seed.get("rumor_id", ""),
                    content=seed.get("content", ""),
                    source=seed.get("source", "pack_seed"),
                )
            elif seed_type == "alliance":
                self.alliance_tracker.add_alliance(
                    alliance_id=seed.get("alliance_id", ""),
                    members=seed.get("members", []),
                    reason=seed.get("reason", "pack_seed"),
                )
