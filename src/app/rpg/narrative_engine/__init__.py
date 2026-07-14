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
from .evidence import (
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
    EvidenceRetrievalResult,
    InMemoryEvidenceSource,
    RetrievalTrace,
)
from .fixtures import bran_fixture_evidence, narrative_fixture_evidence, vexira_fixture_evidence
from .planner import DeterministicBeatPlanner, NarrativePlan
from .profiles import NarrativeProfilePolicy, adaptive_profile, profile_policy
from .projections import journal_projection, legacy_response_projection, transcript_projection, tts_projection
from .renderer import CanonicalNarrativeRenderer, RenderedNarrative, deduplicate_blocks, render_plain_text
from .scene_change import SceneChangeReport, detect_scene_changes

__all__ = [
    "AuthorityClass",
    "BeatKind",
    "BeatPurpose",
    "CanonicalNarrativeRenderer",
    "CanonicalNarrativeResponse",
    "DeliveryMetadata",
    "DeliveryMode",
    "DeterministicBeatPlanner",
    "EvidenceAccessContext",
    "EvidenceBroker",
    "EvidenceLifetime",
    "EvidenceQuery",
    "EvidenceRecord",
    "EvidenceRetrievalResult",
    "GenerationMetadata",
    "InMemoryEvidenceSource",
    "NarrativeBeat",
    "NarrativeBlock",
    "NarrativePlan",
    "NarrativeProfilePolicy",
    "NarrativeSignificance",
    "PresentationProfile",
    "RenderedNarrative",
    "RetrievalTrace",
    "SceneChange",
    "SceneChangeReport",
    "TurnPresentationRequest",
    "ValidationIssue",
    "ValidationReport",
    "VisibilityClass",
    "adaptive_profile",
    "bran_fixture_evidence",
    "canonical_json",
    "deduplicate_blocks",
    "detect_scene_changes",
    "journal_projection",
    "legacy_response_projection",
    "narrative_fixture_evidence",
    "ordered_blocks",
    "profile_policy",
    "render_plain_text",
    "stable_hash",
    "transcript_projection",
    "tts_projection",
    "vexira_fixture_evidence",
]
