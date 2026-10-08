"""Phase 7.5 — Group Reaction Policy.

Decide secondary reactions from participants + crowd state.
Deterministic, rule-based — no randomness.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import CrowdStateView, InteractionParticipant, SecondaryReaction


class GroupReactionPolicy:
    """Decide secondary reactions for non-primary participants."""

    def decide(
        self,
        participants: list[InteractionParticipant],
        primary_decision: dict,
        crowd_state: CrowdStateView,
        coherence_core: Any,
    ) -> list[SecondaryReaction]:
        """Produce secondary reactions for all non-primary participants."""
        reactions: list[SecondaryReaction] = []
        for participant in participants:
            if participant.role == "primary":
                continue
            reaction = self._decide_for_participant(
                participant, primary_decision, crowd_state, coherence_core
            )
            if reaction is not None:
                reactions.append(reaction)
        return reactions

    def _decide_for_participant(
        self,
        participant: InteractionParticipant,
        primary_decision: dict,
        crowd_state: CrowdStateView,
        coherence_core: Any,
    ) -> Optional[SecondaryReaction]:
        """Decide a single participant's reaction.

        Rules:
        - ally → support
        - rival → oppose
        - witness + high tension → spread_rumor
        - witness → observe
        - crowd → observe
        """
        if participant.role == "ally":
            return self._support_reaction(participant)

        if participant.role == "rival":
            return self._oppose_reaction(participant)

        if participant.role == "witness":
            if crowd_state.tension == "high":
                return self._rumor_reaction(participant, crowd_state)
            return self._observe_reaction(participant)

        if participant.role == "crowd":
            return self._observe_reaction(participant)

        return None

    def _support_reaction(
        self, participant: InteractionParticipant
    ) -> SecondaryReaction:
        """Build a support reaction for an ally."""
        return SecondaryReaction(
            npc_id=participant.npc_id,
            reaction_type="support_primary",
            summary=f"{participant.npc_id} supports the primary NPC.",
            emitted_event_types=["npc_secondary_supported"],
            modifiers=["ally_support"],
        )

    def _oppose_reaction(
        self, participant: InteractionParticipant
    ) -> SecondaryReaction:
        """Build an oppose reaction for a rival."""
        return SecondaryReaction(
            npc_id=participant.npc_id,
            reaction_type="oppose_primary",
            summary=f"{participant.npc_id} opposes the primary NPC.",
            emitted_event_types=["npc_secondary_opposed"],
            modifiers=["rival_opposition"],
        )

    def _observe_reaction(
        self, participant: InteractionParticipant
    ) -> SecondaryReaction:
        """Build an observe reaction for a witness or crowd member."""
        return SecondaryReaction(
            npc_id=participant.npc_id,
            reaction_type="observe",
            summary=f"{participant.npc_id} observes the interaction.",
            emitted_event_types=["npc_secondary_observed"],
            modifiers=["passive_observer"],
        )

    def _rumor_reaction(
        self, participant: InteractionParticipant, crowd_state: CrowdStateView
    ) -> SecondaryReaction:
        """Build a rumor-spreading reaction for a witness in a tense scene."""
        return SecondaryReaction(
            npc_id=participant.npc_id,
            reaction_type="spread_rumor",
            summary=f"{participant.npc_id} starts spreading a rumor about the interaction.",
            emitted_event_types=["rumor_seeded"],
            modifiers=["high_tension_witness"],
            metadata={"crowd_tension": crowd_state.tension},
        )
