"""Desktop companion domain package."""

from .attention import DesktopAttentionContext, decide_desktop_attention
from .commentary import (
    CompanionCommentaryLedger,
    build_commentary_candidate,
    commentary_similarity,
    desktop_commentary_prompt,
    normalize_commentary,
)
from .coordinator import (
    DesktopVisionCoordinator,
    DesktopVisionCoordinatorSnapshot,
    DesktopVisionLease,
    DesktopVisionWork,
)
from .memory import DesktopSceneMemory, DesktopSceneMemorySnapshot
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
from .observation import (
    observation_fingerprint,
    parse_desktop_observation,
    redact_observation_diagnostics,
    structured_observation_prompt,
)
from .shadow_watch import ShadowWatchDecision, decide_shadow_watch

__all__ = [
    "CompanionAttentionDecision",
    "CompanionCommentaryCandidate",
    "CompanionCommentaryLedger",
    "CompanionLedgerEntry",
    "CompanionRuntimeStatus",
    "DesktopActivitySignal",
    "DesktopAttentionContext",
    "DesktopBehaviorState",
    "DesktopCompanionPolicy",
    "DesktopObservation",
    "DesktopObservedChange",
    "DesktopObservedValue",
    "DesktopSceneMemory",
    "DesktopSceneMemorySnapshot",
    "DesktopVisionCoordinator",
    "DesktopVisionCoordinatorSnapshot",
    "DesktopVisionLease",
    "DesktopVisionWork",
    "ShadowWatchDecision",
    "build_commentary_candidate",
    "commentary_similarity",
    "decide_desktop_attention",
    "decide_shadow_watch",
    "desktop_commentary_prompt",
    "normalize_commentary",
    "observation_fingerprint",
    "parse_desktop_observation",
    "redact_observation_diagnostics",
    "structured_observation_prompt",
]
