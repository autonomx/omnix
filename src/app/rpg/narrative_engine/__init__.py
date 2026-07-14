"""Unified RPG Narrative Engine.

This package owns future RPG presentation contracts and orchestration. It must
remain independent of legacy prose generators; legacy modules may call into this
package during migration, never the reverse.
"""
from .authority import (
    AuthorityClass,
    BeatKind,
    BeatPurpose,
    DeliveryMode,
    EvidenceLifetime,
    NarrativeSignificance,
    PresentationProfile,
    VisibilityClass,
)
from .contracts import (
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    EvidenceRecord,
    GenerationMetadata,
    NarrativeBeat,
    NarrativeBlock,
    SceneChange,
    TurnPresentationRequest,
    ValidationIssue,
    ValidationReport,
    canonical_json,
    ordered_blocks,
    stable_hash,
)

__all__ = [
    "AuthorityClass",
    "BeatKind",
    "BeatPurpose",
    "CanonicalNarrativeResponse",
    "DeliveryMetadata",
    "DeliveryMode",
    "EvidenceLifetime",
    "EvidenceRecord",
    "GenerationMetadata",
    "NarrativeBeat",
    "NarrativeBlock",
    "NarrativeSignificance",
    "PresentationProfile",
    "SceneChange",
    "TurnPresentationRequest",
    "ValidationIssue",
    "ValidationReport",
    "VisibilityClass",
    "canonical_json",
    "ordered_blocks",
    "stable_hash",
]
