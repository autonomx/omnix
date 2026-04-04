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
        return dict(record.to_dict()) if record is not None else None

    def get_reputation(
        self, state: SocialState, source_id: str, target_id: str
    ) -> dict | None:
        """Get a reputation edge as a dict."""
        from .reputation_graph import ReputationGraph

        graph = ReputationGraph()
        edge = graph.get_edge(state, source_id, target_id)
        return dict(edge.to_dict()) if edge is not None else None

    def get_active_rumors_for_subject(
        self, state: SocialState, subject_id: str
    ) -> list[dict]:
        """Get all active rumors about a subject."""
        results = []
        for rumor in state.rumors.values():
            if rumor.active and rumor.subject_id == subject_id:
                results.append(dict(rumor.to_dict()))
        return results

    def get_alliance(
        self, state: SocialState, entity_a: str, entity_b: str
    ) -> dict | None:
        """Get an alliance record as a dict."""
        from .alliance_tracker import AllianceTracker

        tracker = AllianceTracker()
        record = tracker.get(state, entity_a, entity_b)
        return dict(record.to_dict()) if record is not None else None

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

    # ------------------------------------------------------------------
    # Phase 8.2 — Encounter seeding helpers
    # ------------------------------------------------------------------

    def get_hostile_entities_in_scene(
        self, state: SocialState, entity_ids: list[str], player_id: str = "player"
    ) -> list[str]:
        """Return entity_ids with hostile relationship toward the player."""
        from .relationship_tracker import RelationshipTracker
        tracker = RelationshipTracker()
        hostile: list[str] = []
        for eid in entity_ids:
            if eid == player_id:
                continue
            record = tracker.get(state, eid, player_id)
            if record is not None and record.status in ("hostile", "enemy"):
                hostile.append(eid)
        return sorted(hostile)

    def get_allied_entities_in_scene(
        self, state: SocialState, entity_ids: list[str], player_id: str = "player"
    ) -> list[str]:
        """Return entity_ids allied with the player."""
        from .alliance_tracker import AllianceTracker
        tracker = AllianceTracker()
        allied: list[str] = []
        for eid in entity_ids:
            if eid == player_id:
                continue
            record = tracker.get(state, player_id, eid)
            if record is not None and record.status == "active":
                allied.append(eid)
        return sorted(allied)

    def get_pressure_relationships(
        self, state: SocialState, entity_ids: list[str]
    ) -> dict:
        """Return a summary of relationship pressure among entities."""
        from .relationship_tracker import RelationshipTracker
        tracker = RelationshipTracker()
        pressure: dict = {"hostile_count": 0, "allied_count": 0, "neutral_count": 0}
        for i, a in enumerate(entity_ids):
            for b in entity_ids[i + 1:]:
                record = tracker.get(state, a, b)
                if record is None:
                    pressure["neutral_count"] += 1
                elif record.status in ("hostile", "enemy"):
                    pressure["hostile_count"] += 1
                elif record.status in ("allied", "friendly"):
                    pressure["allied_count"] += 1
                else:
                    pressure["neutral_count"] += 1
        return pressure

    # ------------------------------------------------------------------
    # Phase 8.3 — World simulation seeding helpers
    # ------------------------------------------------------------------

    def get_known_factions(self, state: SocialState) -> list[str]:
        """Return known faction IDs from alliances and relationships."""
        factions: set[str] = set()
        for alliance in state.alliances.values():
            for eid in (
                getattr(alliance, "entity_a", None),
                getattr(alliance, "entity_b", None),
            ):
                if eid:
                    factions.add(eid)
        return sorted(factions)

    def get_recent_rumors(
        self, state: SocialState, limit: int = 5
    ) -> list[dict]:
        """Return active rumors, newest first, up to limit."""
        active = [
            dict(rumor.to_dict())
            for rumor in state.rumors.values()
            if rumor.active
        ]
        return active[:limit]

    def get_faction_pressure_map(self, state: SocialState) -> dict[str, str]:
        """Derive faction pressure from relationship hostility."""
        pressure: dict[str, str] = {}
        for rel in state.relationships.values():
            status = getattr(rel, "status", "")
            source = getattr(rel, "source_id", "")
            if status in ("hostile", "enemy") and source:
                pressure[source] = "high"
        return pressure

    def get_relationship_hotspots(self, state: SocialState) -> list[dict]:
        """Return a list of high-tension relationship pairs."""
        hotspots: list[dict] = []
        for rel in state.relationships.values():
            status = getattr(rel, "status", "")
            if status in ("hostile", "enemy", "rival"):
                hotspots.append({
                    "source_id": getattr(rel, "source_id", ""),
                    "target_id": getattr(rel, "target_id", ""),
                    "status": status,
                })
        return hotspots
