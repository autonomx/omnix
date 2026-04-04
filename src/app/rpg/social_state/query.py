"""Phase 7.6 — Social State Query API.

Provide read/query API for NPC agency, presenters, and dashboards.
All methods return plain dicts suitable for JSON serialization.
"""

from __future__ import annotations

from .models import SocialState


class SocialStateQuery:
    """Read-only query API for persistent social state."""

    def get_relationship(
        self, state: SocialState, source_id: str, target_id: str
    ) -> dict | None:
        """Get a relationship record as a dict."""
        from .relationship_tracker import RelationshipTracker

        tracker = RelationshipTracker()
        record = tracker.get(state, source_id, target_id)
        return record.to_dict() if record is not None else None

    def get_reputation(
        self, state: SocialState, source_id: str, target_id: str
    ) -> dict | None:
        """Get a reputation edge as a dict."""
        from .reputation_graph import ReputationGraph

        graph = ReputationGraph()
        edge = graph.get_edge(state, source_id, target_id)
        return edge.to_dict() if edge is not None else None

    def get_active_rumors_for_subject(
        self, state: SocialState, subject_id: str
    ) -> list[dict]:
        """Get all active rumors about a subject."""
        results = []
        for rumor in state.rumors.values():
            if rumor.active and rumor.subject_id == subject_id:
                results.append(rumor.to_dict())
        return results

    def get_alliance(
        self, state: SocialState, entity_a: str, entity_b: str
    ) -> dict | None:
        """Get an alliance record as a dict."""
        from .alliance_tracker import AllianceTracker

        tracker = AllianceTracker()
        record = tracker.get(state, entity_a, entity_b)
        return record.to_dict() if record is not None else None

    def build_npc_social_view(
        self, state: SocialState, npc_id: str, target_id: str | None = None
    ) -> dict:
        """Build a composite social view for an NPC.

        Includes relationship, reputation, and active rumors relevant
        to the NPC.
        """
        view: dict = {
            "npc_id": npc_id,
            "target_id": target_id,
            "relationship": None,
            "reputation": None,
            "active_rumors": [],
        }

        if target_id is not None:
            view["relationship"] = self.get_relationship(state, npc_id, target_id)
            view["reputation"] = self.get_reputation(state, target_id, npc_id)

        view["active_rumors"] = self.get_active_rumors_for_subject(state, npc_id)

        return view
