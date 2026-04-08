"""Phase 7.5 — Group Dynamics Engine.

Orchestrate participant finding, crowd state, secondary reactions,
and rumor seeds for multi-actor social interactions.
"""

from __future__ import annotations

from typing import Any, Optional

from .alliance_logic import AllianceLogic
from .crowd_state import CrowdStateBuilder
from .models import CrowdStateView, RumorSeed, SecondaryReaction
from .participant_finder import ParticipantFinder
from .reaction_policy import GroupReactionPolicy
from .rumor_seed_builder import RumorSeedBuilder

# Supported group dynamics event types
SUPPORTED_GROUP_EVENT_TYPES = frozenset({
    "npc_secondary_supported",
    "npc_secondary_opposed",
    "npc_secondary_observed",
    "rumor_seeded",
})


class GroupDynamicsEngine:
    """Orchestrate multi-actor social interaction dynamics."""

    def __init__(
        self,
        participant_finder: Optional[ParticipantFinder] = None,
        alliance_logic: Optional[AllianceLogic] = None,
        crowd_builder: Optional[CrowdStateBuilder] = None,
        reaction_policy: Optional[GroupReactionPolicy] = None,
        rumor_builder: Optional[RumorSeedBuilder] = None,
    ) -> None:
        self.participant_finder = participant_finder or ParticipantFinder()
        self.alliance_logic = alliance_logic or AllianceLogic()
        self.crowd_builder = crowd_builder or CrowdStateBuilder()
        self.reaction_policy = reaction_policy or GroupReactionPolicy()
        self.rumor_builder = rumor_builder or RumorSeedBuilder()

    def resolve_group_dynamics(
        self,
        primary_npc_id: str,
        primary_decision: dict,
        coherence_core: Any,
    ) -> dict:
        """Resolve group dynamics for a social interaction.

        Returns:
            {
                "participants": [...],
                "crowd_state": {...},
                "secondary_reactions": [...],
                "rumor_seeds": [...],
                "events": [...],
            }
        """
        # 1. Find participants
        participants = self.participant_finder.find(primary_npc_id, coherence_core)

        # FIX #5: Ensure deterministic ordering
        participants = sorted(participants, key=lambda p: p.npc_id)

        # 2. Build crowd state
        crowd_state = self.crowd_builder.build(coherence_core)

        # 3. Decide secondary reactions
        reactions = self.reaction_policy.decide(
            participants, primary_decision, crowd_state, coherence_core
        )

        # FIX #5: Ensure deterministic ordering of reactions
        reactions = sorted(reactions, key=lambda r: r.npc_id)

        # 4. Build rumor seeds
        rumor_seeds = self.rumor_builder.build(
            reactions, primary_decision, coherence_core
        )

        # 5. Build events
        events = self._reaction_events(reactions) + self._rumor_events(rumor_seeds)

        return {
            "participants": [p.to_dict() for p in participants],
            "crowd_state": crowd_state.to_dict(),
            "secondary_reactions": [r.to_dict() for r in reactions],
            "rumor_seeds": [s.to_dict() for s in rumor_seeds],
            "events": events,
        }

    def _reaction_events(self, reactions: list[SecondaryReaction]) -> list[dict]:
        """Convert secondary reactions into emittable events."""
        events: list[dict] = []
        for reaction in reactions:
            for event_type in reaction.emitted_event_types:
                if event_type not in SUPPORTED_GROUP_EVENT_TYPES:
                    continue
                events.append({
                    "type": event_type,
                    "payload": {
                        "npc_id": reaction.npc_id,
                        "reaction_type": reaction.reaction_type,
                        "summary": reaction.summary,
                        "modifiers": list(reaction.modifiers),
                        "source": "group_dynamics",
                    },
                })
        return events

    def _rumor_events(self, rumor_seeds: list[RumorSeed]) -> list[dict]:
        """Convert rumor seeds into emittable events."""
        events: list[dict] = []
        for seed in rumor_seeds:
            events.append({
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": seed.rumor_id,
                    "source_npc_id": seed.source_npc_id,
                    "subject_id": seed.subject_id,
                    "rumor_type": seed.rumor_type,
                    "summary": seed.summary,
                    "location": seed.location,
                    "source": "group_dynamics",
                },
            })
        return events
