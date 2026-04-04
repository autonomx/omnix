"""Phase 7.5 — Alliance Logic.

Simple deterministic checks for ally/rival support patterns.
"""

from __future__ import annotations

from typing import Any

from .models import InteractionParticipant


class AllianceLogic:
    """Deterministic ally/rival support rules."""

    def supports_primary(
        self,
        participant: InteractionParticipant,
        primary_decision: dict,
        coherence_core: Any,
    ) -> bool:
        """Return True if the participant is likely to support the primary NPC."""
        if participant.role == "primary":
            return False  # Primary cannot support itself

        if participant.role == "ally":
            return True

        if participant.relationship_to_primary == "friendly":
            return True

        return False

    def opposes_primary(
        self,
        participant: InteractionParticipant,
        primary_decision: dict,
        coherence_core: Any,
    ) -> bool:
        """Return True if the participant is likely to oppose the primary NPC."""
        if participant.role == "primary":
            return False

        if participant.role == "rival":
            return True

        if self._rivalry_bias(participant):
            return True

        return False

    def _same_faction_bias(
        self,
        participant: InteractionParticipant,
        primary_npc_id: str,
        coherence_core: Any,
    ) -> bool:
        """Check if participant shares a faction with the primary NPC."""
        if not participant.faction_id:
            return False
        try:
            state = coherence_core.get_state()
            for fact in state.stable_world_facts.values():
                subject = getattr(fact, "subject", "")
                predicate = getattr(fact, "predicate", "")
                value = getattr(fact, "value", None)
                if (
                    subject == primary_npc_id
                    and predicate == "faction"
                    and str(value) == participant.faction_id
                ):
                    return True
        except (AttributeError, TypeError):
            pass
        return False

    def _rivalry_bias(self, participant: InteractionParticipant) -> bool:
        """Check if participant has hostile relationship indicators."""
        return participant.relationship_to_primary == "hostile"
