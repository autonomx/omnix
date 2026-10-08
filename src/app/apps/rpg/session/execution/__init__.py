"""Phase 7.3 — Scene Execution Layer.

This package provides structured action resolution for player choices.
Selected options resolve into deterministic events that flow through
the existing EventBus → CoherenceCore reducer path.

Key rule: option selection never mutates state directly.
"""

from __future__ import annotations

from .consequences import ConsequenceBuilder
from .intent_mapping import ActionIntentMapper
from .models import (
    ActionConsequence,
    ActionResolutionResult,
    ResolvedAction,
    SceneTransition,
)
from .resolver import ActionResolver
from .transitions import SceneTransitionBuilder

__all__ = [
    "ActionConsequence",
    "ActionResolutionResult",
    "ResolvedAction",
    "SceneTransition",
    "ActionIntentMapper",
    "ConsequenceBuilder",
    "SceneTransitionBuilder",
    "ActionResolver",
]
