"""Phase 8.4 — Debug / Analytics / GM Inspection.

Stable export surface for the debug layer.

This package is **read-only** and **non-authoritative**.  It explains
the game from already-available structured inputs — it never mutates
game state or creates new truth.
"""

from .core import DebugCore
from .models import (
    SUPPORTED_DEBUG_NODE_TYPES,
    SUPPORTED_DEBUG_SCOPES,
    ChoiceExplanation,
    DebugTrace,
    DebugTraceNode,
    EncounterExplanation,
    GMInspectionBundle,
    NPCResponseExplanation,
    WorldSimExplanation,
)
from .presenter import DebugPresenter
from .trace_builder import DebugTraceBuilder

__all__ = [
    "DebugCore",
    "DebugTraceBuilder",
    "DebugPresenter",
    "DebugTrace",
    "DebugTraceNode",
    "ChoiceExplanation",
    "NPCResponseExplanation",
    "EncounterExplanation",
    "WorldSimExplanation",
    "GMInspectionBundle",
    "SUPPORTED_DEBUG_NODE_TYPES",
    "SUPPORTED_DEBUG_SCOPES",
]
