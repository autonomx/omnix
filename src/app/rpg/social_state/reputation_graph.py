"""Phase 7.6 — Reputation Graph.

Manage persistent reputation edges between entities.
Scores are clamped to [-1.0, 1.0].
"""

from __future__ import annotations

from .models import ReputationEdge, SocialState


class ReputationGraph:
    """Manage persistent reputation edges."""

    def get_edge(
        self, state: SocialState, source_id: str, target_id: str
    ) -> ReputationEdge | None:
        """Look up a reputation edge."""
        edge_id = self._edge_id(source_id, target_id)
        return state.reputation_edges.get(edge_id)

    def upsert_edge(self, state: SocialState, edge: ReputationEdge) -> None:
        """Insert or replace a reputation edge."""
        edge_id = self._edge_id(edge.source_id, edge.target_id)
        state.reputation_edges[edge_id] = edge

    def adjust_score(
        self,
        state: SocialState,
        source_id: str,
        target_id: str,
        delta: float,
        event_id: str | None = None,
        metadata: dict | None = None,
    ) -> ReputationEdge:
        """Adjust the score of a reputation edge, creating it if needed.

        Score is clamped to [-1.0, 1.0].
        """
        edge_id = self._edge_id(source_id, target_id)
        edge = state.reputation_edges.get(edge_id)
        if edge is None:
            edge = ReputationEdge(source_id=source_id, target_id=target_id)
        edge.score = max(-1.0, min(1.0, edge.score + delta))
        if event_id is not None:
            edge.last_event_id = event_id
        if metadata:
            edge.metadata.update(metadata)
        state.reputation_edges[edge_id] = edge
        return edge

    def _edge_id(self, source_id: str, target_id: str) -> str:
        """Generate a deterministic edge key."""
        return f"rep:{source_id}:{target_id}"
