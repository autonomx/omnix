"""Phase 6.5 — UX Recovery Layer.

Provides graceful degradation for parser, director, renderer, and
coherence failures. Keeps CoherenceCore as truth owner and builds
fallback scenes grounded in coherence summaries and last-good anchors.
"""

from .ambiguity import AmbiguityPolicy
from .fallbacks import FallbackSceneBuilder
from .manager import RecoveryManager
from .models import (
    AmbiguityDecision,
    RecoveryReason,
    RecoveryRecord,
    RecoveryResult,
    RecoveryState,
)

__all__ = [
    "RecoveryManager",
    "RecoveryState",
    "RecoveryRecord",
    "RecoveryResult",
    "RecoveryReason",
    "AmbiguityDecision",
    "AmbiguityPolicy",
    "FallbackSceneBuilder",
]
