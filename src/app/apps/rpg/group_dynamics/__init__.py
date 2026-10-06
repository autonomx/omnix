"""Phase 7.5 — Multi-Actor Interaction & Group Dynamics.

Scene-level social dynamics: participant modeling, alliance logic,
crowd state, deterministic group reaction policy, and rumor seeding.
"""

from .alliance_logic import AllianceLogic
from .crowd_state import CrowdStateBuilder
from .group_engine import GroupDynamicsEngine
from .models import CrowdStateView, InteractionParticipant, RumorSeed, SecondaryReaction
from .participant_finder import ParticipantFinder
from .reaction_policy import GroupReactionPolicy
from .rumor_seed_builder import RumorSeedBuilder

__all__ = [
    "InteractionParticipant",
    "SecondaryReaction",
    "CrowdStateView",
    "RumorSeed",
    "ParticipantFinder",
    "AllianceLogic",
    "CrowdStateBuilder",
    "GroupReactionPolicy",
    "RumorSeedBuilder",
    "GroupDynamicsEngine",
]
