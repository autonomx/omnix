"""Phase 7.6 — Persistent Social State & Reputation System.

This package provides explicit persistent state for reputation edges,
relationship metrics, rumor records, and alliance records.
Social state is parallel to coherence — not inside it.

Key rule: social state is updated only through event reducers.
NPC agency may read social state but does not own it.
"""

from __future__ import annotations

from .alliance_tracker import AllianceTracker
from .core import SocialStateCore
from .models import (
    AllianceRecord,
    RelationshipStateRecord,
    ReputationEdge,
    RumorRecord,
    SocialState,
)
from .query import SocialStateQuery
from .relationship_tracker import RelationshipTracker
from .reputation_graph import ReputationGraph
from .rumor_log import RumorLog

__all__ = [
    "ReputationEdge",
    "RelationshipStateRecord",
    "RumorRecord",
    "AllianceRecord",
    "SocialState",
    "ReputationGraph",
    "RelationshipTracker",
    "RumorLog",
    "AllianceTracker",
    "SocialStateQuery",
    "SocialStateCore",
]
