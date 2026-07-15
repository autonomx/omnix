"""Desktop companion domain package."""

from .coordinator import (
    DesktopVisionCoordinator,
    DesktopVisionCoordinatorSnapshot,
    DesktopVisionLease,
    DesktopVisionWork,
)
from .models import (
    CompanionAttentionDecision,
    CompanionCommentaryCandidate,
    CompanionLedgerEntry,
    CompanionRuntimeStatus,
    DesktopActivitySignal,
    DesktopBehaviorState,
    DesktopCompanionPolicy,
    DesktopObservation,
    DesktopObservedChange,
    DesktopObservedValue,
)
from .shadow_watch import ShadowWatchDecision, decide_shadow_watch

__all__ = [
    "CompanionAttentionDecision",
    "CompanionCommentaryCandidate",
    "CompanionLedgerEntry",
    "CompanionRuntimeStatus",
    "DesktopActivitySignal",
    "DesktopBehaviorState",
    "DesktopCompanionPolicy",
    "DesktopObservation",
    "DesktopObservedChange",
    "DesktopObservedValue",
    "DesktopVisionCoordinator",
    "DesktopVisionCoordinatorSnapshot",
    "DesktopVisionLease",
    "DesktopVisionWork",
    "ShadowWatchDecision",
    "decide_shadow_watch",
]
