"""Phase 6.5 — Social Simulation.

Provides deterministic social systems for NPCs and factions:
- reputation_graph: Inter-entity reputation tracking
- alliance_system: Faction alliances and strength
- betrayal_propagation: Betrayal social fallout
- rumor_system: Deterministic rumor spread
- group_decision: Faction stance aggregation
"""

from .alliance_system import AllianceSystem
from .betrayal_propagation import BetrayalPropagation
from .group_decision import GroupDecisionEngine
from .reputation_graph import ReputationGraph
from .rumor_system import RumorSystem

__all__ = [
    "ReputationGraph",
    "AllianceSystem",
    "BetrayalPropagation",
    "RumorSystem",
    "GroupDecisionEngine",
]