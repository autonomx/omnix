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
from .projections import (
    journal_projection,
    legacy_response_projection,
    transcript_projection,
    tts_projection,
)
from .renderer import (
    CanonicalNarrativeRenderer,
    RenderedNarrative,
    deduplicate_blocks,
    render_plain_text,
)

__all__ = [
    "AuthorityClass",
    "BeatKind",
    "BeatPurpose",
    "CanonicalNarrativeRenderer",
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
    "RenderedNarrative",
    "SceneChange",
    "TurnPresentationRequest",
    "ValidationIssue",
    "ValidationReport",
    "VisibilityClass",
    "canonical_json",
    "deduplicate_blocks",
    "journal_projection",
    "legacy_response_projection",
    "ordered_blocks",
    "render_plain_text",
    "stable_hash",
    "transcript_projection",
    "tts_projection",
]
