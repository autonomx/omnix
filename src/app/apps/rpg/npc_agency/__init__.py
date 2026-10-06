"""Phase 7.4 — NPC Agency & Social Response.

This package provides structured NPC decision logic for social interactions.
NPC responses are decision-driven, deterministic, and inspectable.

Key rule: NPC agency emits structured events only — no direct coherence mutation.
"""

from __future__ import annotations

from .agency_engine import NPCAgencyEngine
from .decision_policy import NPCDecisionPolicy
from .models import (
    FactionAlignmentView,
    NPCDecisionContext,
    NPCDecisionResult,
    NPCRelationshipView,
)
from .response_builder import NPCResponseBuilder

__all__ = [
    "NPCDecisionContext",
    "NPCDecisionResult",
    "NPCRelationshipView",
    "FactionAlignmentView",
    "NPCDecisionPolicy",
    "NPCResponseBuilder",
    "NPCAgencyEngine",
]
