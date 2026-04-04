"""Phase 7.5 — Rumor Seed Builder.

Produce structured rumor seeds from witness/crowd reactions.
Only seeds — no propagation system yet.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import RumorSeed, SecondaryReaction


class RumorSeedBuilder:
    """Build rumor seeds from secondary reactions."""

    def build(
        self,
        secondary_reactions: list[SecondaryReaction],
        primary_decision: dict,
        coherence_core: Any,
    ) -> list[RumorSeed]:
        """Create rumor seeds from reactions that qualify.

        Only 'spread_rumor' reactions produce seeds.
        Optionally, 'oppose_primary' in high-tension scenes may also
        seed rumors (reserved for later phases).
        """
        location = self._get_current_location(coherence_core)

        seeds: list[RumorSeed] = []
        for reaction in secondary_reactions:
            if reaction.reaction_type == "spread_rumor":
                seed = self._reaction_to_rumor(reaction, primary_decision, location)
                if seed is not None:
                    seeds.append(seed)
        return seeds

    def _reaction_to_rumor(
        self,
        reaction: SecondaryReaction,
        primary_decision: dict,
        location: Optional[str],
    ) -> Optional[RumorSeed]:
        """Convert a single reaction into a rumor seed."""
        primary_npc_id = primary_decision.get("npc_id")
        outcome = primary_decision.get("outcome", "unknown")

        rumor_id = f"rumor:{reaction.npc_id}:{primary_npc_id or 'unknown'}"
        summary = (
            f"{reaction.npc_id} spreads word about "
            f"{primary_npc_id or 'an NPC'}'s {outcome} response."
        )

        return RumorSeed(
            rumor_id=rumor_id,
            source_npc_id=reaction.npc_id,
            subject_id=primary_npc_id,
            rumor_type="interaction_outcome",
            summary=summary,
            location=location,
            metadata={
                "primary_outcome": outcome,
                "reaction_modifiers": list(reaction.modifiers),
            },
        )

    @staticmethod
    def _get_current_location(coherence_core: Any) -> Optional[str]:
        """Extract the current location from coherence state."""
        try:
            state = coherence_core.get_state()
            location_fact = state.stable_world_facts.get("scene:location")
            if location_fact:
                return getattr(location_fact, "value", None)
        except (AttributeError, TypeError):
            pass
        return None
