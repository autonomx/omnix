"""Phase 7.4 — NPC Agency & Social Response.

This package provides structured NPC decision logic for social interactions.
NPC responses are decision-driven, deterministic, and inspectable.

Key rule: NPC agency emits structured events only — no direct coherence mutation.
"""

from __future__ import annotations

from .models import (
    FactionAlignmentView,
    NPCDecisionContext,
    NPCDecisionResult,
    NPCRelationshipView,
)
from .decision_policy import NPCDecisionPolicy
from .response_builder import NPCResponseBuilder
from .agency_engine import NPCAgencyEngine

__all__ = [
    "NPCDecisionContext",
    "NPCDecisionResult",
    "NPCRelationshipView",
    "FactionAlignmentView",
    "NPCDecisionPolicy",
    "NPCResponseBuilder",
    "NPCAgencyEngine",
]
