"""Phase 7.5 — Participant Finder.

Identify who else is socially relevant in the current scene.
Deterministic, conservative classification of scene actors.
"""

from __future__ import annotations

from typing import Any

from .models import InteractionParticipant


class ParticipantFinder:
    """Find and classify interaction participants from the current scene."""

    def find(
        self, primary_npc_id: str, coherence_core: Any
    ) -> list[InteractionParticipant]:
        """Return all interaction participants for the current scene.

        The primary NPC is always included with role 'primary'.
        Other scene actors are classified as ally/rival/witness/crowd.
        """
        scene_npc_ids = self._scene_participants(coherence_core)

        participants: list[InteractionParticipant] = []

        # Always include the primary NPC
        participants.append(
            InteractionParticipant(
                npc_id=primary_npc_id,
                role="primary",
                faction_id=self._extract_faction_id(primary_npc_id, coherence_core),
                relationship_to_primary="self",
                relationship_to_player=self._relationship_to_player(
                    primary_npc_id, coherence_core
                ),
            )
        )

        # Classify other scene actors
        for npc_id in scene_npc_ids:
            if npc_id == primary_npc_id:
                continue
            # Exclude the player entity
            if npc_id == "player":
                continue

            role = self._classify_role(npc_id, primary_npc_id, coherence_core)
            participants.append(
                InteractionParticipant(
                    npc_id=npc_id,
                    role=role,
                    faction_id=self._extract_faction_id(npc_id, coherence_core),
                    relationship_to_primary=self._relationship_to_primary(
                        npc_id, primary_npc_id, coherence_core
                    ),
                    relationship_to_player=self._relationship_to_player(
                        npc_id, coherence_core
                    ),
                )
            )

        return participants

    def _scene_participants(self, coherence_core: Any) -> list[str]:
        """Get current scene actor IDs from coherence."""
        try:
            state = coherence_core.get_state()
            # Check scene anchor for present_actors
            anchors = getattr(state, "scene_anchors", [])
            if anchors:
                latest = anchors[-1]
                actors = (
                    latest.get("present_actors", [])
                    if isinstance(latest, dict)
                    else getattr(latest, "present_actors", [])
                )
                return list(actors)
        except (AttributeError, TypeError, IndexError):
            pass
        return []

    def _classify_role(
        self, npc_id: str, primary_npc_id: str, coherence_core: Any
    ) -> str:
        """Classify an NPC's role relative to the primary NPC.

        Simple deterministic rules:
        - Same faction as primary → ally
        - Known hostile relationship → rival
        - Otherwise → witness
        """
        primary_faction = self._extract_faction_id(primary_npc_id, coherence_core)
        npc_faction = self._extract_faction_id(npc_id, coherence_core)

        # Same faction → ally
        if primary_faction and npc_faction and primary_faction == npc_faction:
            return "ally"

        # Check for hostile relationship
        rel = self._relationship_to_primary(npc_id, primary_npc_id, coherence_core)
        if rel == "hostile":
            return "rival"

        return "witness"

    def _relationship_to_primary(
        self, npc_id: str, primary_npc_id: str, coherence_core: Any
    ) -> str:
        """Determine relationship between an NPC and the primary NPC."""
        try:
            state = coherence_core.get_state()
            for fact in state.stable_world_facts.values():
                subject = getattr(fact, "subject", "")
                predicate = getattr(fact, "predicate", "")
                value = getattr(fact, "value", None)
                if (
                    subject == npc_id
                    and predicate == "relationship"
                    and isinstance(value, dict)
                    and value.get("target") == primary_npc_id
                ):
                    return str(value.get("stance", "neutral"))
        except (AttributeError, TypeError):
            pass
        return "neutral"

    def _relationship_to_player(self, npc_id: str, coherence_core: Any) -> str:
        """Determine relationship between an NPC and the player."""
        try:
            state = coherence_core.get_state()
            for fact in state.stable_world_facts.values():
                subject = getattr(fact, "subject", "")
                predicate = getattr(fact, "predicate", "")
                value = getattr(fact, "value", None)
                if (
                    subject == npc_id
                    and predicate == "relationship"
                    and isinstance(value, dict)
                    and value.get("target") == "player"
                ):
                    return str(value.get("stance", "neutral"))
        except (AttributeError, TypeError):
            pass
        return "neutral"

    def _extract_faction_id(self, npc_id: str, coherence_core: Any) -> str | None:
        """Extract the faction ID for an NPC from coherence facts."""
        try:
            state = coherence_core.get_state()
            for fact in state.stable_world_facts.values():
                subject = getattr(fact, "subject", "")
                predicate = getattr(fact, "predicate", "")
                value = getattr(fact, "value", None)
                if subject == npc_id and predicate == "faction":
                    return str(value) if value else None
        except (AttributeError, TypeError):
            pass
        return None
