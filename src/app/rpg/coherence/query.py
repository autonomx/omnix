from __future__ import annotations

from typing import List

from .models import CoherenceState, EntityCoherenceView


class CoherenceQueryAPI:
    def __init__(self, state: CoherenceState) -> None:
        self.state = state

    def get_scene_summary(self) -> dict:
        location_fact = self.state.scene_facts.get("scene:location")
        anchor = self.state.continuity_anchors[-1] if self.state.continuity_anchors else None
        return {
            "location": location_fact.value if location_fact else None,
            "summary": anchor.summary if anchor else "",
            "present_actors": anchor.present_actors if anchor else [],
            "active_tensions": anchor.active_tensions if anchor else [],
        }

    def get_active_tensions(self) -> list:
        anchor = self.state.continuity_anchors[-1] if self.state.continuity_anchors else None
        if not anchor:
            return []
        return [{"text": t} for t in anchor.active_tensions]

    def get_unresolved_threads(self) -> list:
        return [t.to_dict() for t in self.state.unresolved_threads.values() if t.status != "resolved"]

    def get_actor_commitments(self, actor_id: str) -> list:
        records: List[dict] = []
        for bucket in (self.state.player_commitments, self.state.npc_commitments):
            for commitment in bucket.values():
                if commitment.actor_id == actor_id and commitment.status == "active":
                    records.append(commitment.to_dict())
        return records

    def get_known_facts(self, entity_id: str) -> dict:
        facts: List[dict] = []
        for bucket in (
            self.state.stable_world_facts,
            self.state.scene_facts,
            self.state.temporary_assumptions,
        ):
            for fact in bucket.values():
                if fact.subject == entity_id:
                    facts.append(fact.to_dict())
        return {"entity_id": entity_id, "facts": facts}

    def get_recent_consequences(self, limit: int = 10) -> list:
        return [c.to_dict() for c in self.state.recent_changes[-limit:]]

    def get_last_good_anchor(self) -> dict | None:
        if not self.state.continuity_anchors:
            return None
        return self.state.continuity_anchors[-1].to_dict()

    def get_entity_view(self, entity_id: str) -> dict:
        facts = self.get_known_facts(entity_id).get("facts", [])
        commitments = self.get_actor_commitments(entity_id)
        consequences = [
            c.to_dict()
            for c in self.state.recent_changes
            if entity_id in c.entity_ids
        ]
        return EntityCoherenceView(
            entity_id=entity_id,
            facts=facts,
            commitments=commitments,
            recent_consequences=consequences,
        ).to_dict()

    # ------------------------------------------------------------------
    # Phase 8.2 — Encounter seeding helpers
    # ------------------------------------------------------------------

    def get_scene_entities(self) -> list[str]:
        """Return entity IDs present in the current scene."""
        anchor = self.state.continuity_anchors[-1] if self.state.continuity_anchors else None
        if not anchor:
            return []
        return list(anchor.present_actors)

    def get_location_hazards(self) -> list[dict]:
        """Return hazard facts for the current scene location."""
        hazards: list[dict] = []
        for key, fact in self.state.scene_facts.items():
            if "hazard" in key.lower() or "danger" in key.lower():
                hazards.append(fact.to_dict())
        return hazards

    def get_relevant_points_of_interest(self) -> list[dict]:
        """Return points of interest in the current scene."""
        pois: list[dict] = []
        for key, fact in self.state.scene_facts.items():
            if "poi" in key.lower() or "point_of_interest" in key.lower() or "clue" in key.lower():
                pois.append(fact.to_dict())
        return pois

    def get_immediate_threats(self) -> list[dict]:
        """Return active tensions / threats from the latest anchor."""
        anchor = self.state.continuity_anchors[-1] if self.state.continuity_anchors else None
        if not anchor:
            return []
        return [{"text": t} for t in anchor.active_tensions]
