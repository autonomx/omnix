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
from .campaign_bible import (
    CampaignBibleEvidenceSource,
    CampaignBibleSnapshot,
    campaign_bible_evidence,
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
from .delivery import NarrativeDeliveryCoordinator
from .evidence import (
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
    EvidenceRetrievalResult,
    InMemoryEvidenceSource,
    RetrievalTrace,
)
from .fixtures import bran_fixture_evidence, narrative_fixture_evidence, vexira_fixture_evidence
from .hermes_research import (
    HermesNarrativeResearcher,
    HermesResearchFinding,
    HermesResearchPolicy,
    HermesResearchRequest,
    HermesResearchResult,
    HermesResearchSource,
    normalize_hermes_research,
    run_bounded_hermes_research,
)
from .planner import DeterministicBeatPlanner, NarrativePlan
from .profiles import NarrativeProfilePolicy, adaptive_profile, profile_policy
from .projections import journal_projection, legacy_response_projection, transcript_projection, tts_projection
from .renderer import CanonicalNarrativeRenderer, RenderedNarrative, deduplicate_blocks, render_plain_text
from .repository import (
    InMemoryNarrativeResponseRepository,
    NarrativeResponseConflict,
    NarrativeResponseRepository,
)
from .scene_change import SceneChangeReport, detect_scene_changes
from .service import NarrativeEngineResult, NarrativeEngineService
from .validation import NarrativeRepairer, NarrativeValidator, ValidatedWriterResult, write_validate_repair
from .world_forge import (
    WorldForgeAudit,
    WorldForgeIssue,
    WorldForgeProposal,
    apply_world_forge_proposal,
    audit_world_forge_proposal,
)
from .writer import (
    DeterministicNarrativeWriter,
    NarrativeWriter,
    StructuredNarrativeWriter,
    WriterResult,
    parse_structured_blocks,
    writer_payload,
)

__all__ = [
    "AuthorityClass",
    "BeatKind",
    "BeatPurpose",
    "CampaignBibleEvidenceSource",
    "CampaignBibleSnapshot",
    "CanonicalNarrativeRenderer",
    "CanonicalNarrativeResponse",
    "DeliveryMetadata",
    "DeliveryMode",
    "DeterministicBeatPlanner",
    "DeterministicNarrativeWriter",
    "EvidenceAccessContext",
    "EvidenceBroker",
    "EvidenceLifetime",
    "EvidenceQuery",
    "EvidenceRecord",
    "EvidenceRetrievalResult",
    "GenerationMetadata",
    "HermesNarrativeResearcher",
    "HermesResearchFinding",
    "HermesResearchPolicy",
    "HermesResearchRequest",
    "HermesResearchResult",
    "HermesResearchSource",
    "InMemoryEvidenceSource",
    "InMemoryNarrativeResponseRepository",
    "NarrativeBeat",
    "NarrativeBlock",
    "NarrativeDeliveryCoordinator",
    "NarrativeEngineResult",
    "NarrativeEngineService",
    "NarrativePlan",
    "NarrativeProfilePolicy",
    "NarrativeRepairer",
    "NarrativeResponseConflict",
    "NarrativeResponseRepository",
    "NarrativeSignificance",
    "NarrativeValidator",
    "NarrativeWriter",
    "PresentationProfile",
    "RenderedNarrative",
    "RetrievalTrace",
    "SceneChange",
    "SceneChangeReport",
    "StructuredNarrativeWriter",
    "TurnPresentationRequest",
    "ValidatedWriterResult",
    "ValidationIssue",
    "ValidationReport",
    "VisibilityClass",
    "WorldForgeAudit",
    "WorldForgeIssue",
    "WorldForgeProposal",
    "WriterResult",
    "adaptive_profile",
    "apply_world_forge_proposal",
    "audit_world_forge_proposal",
    "bran_fixture_evidence",
    "campaign_bible_evidence",
    "canonical_json",
    "deduplicate_blocks",
    "detect_scene_changes",
    "journal_projection",
    "legacy_response_projection",
    "narrative_fixture_evidence",
    "normalize_hermes_research",
    "ordered_blocks",
    "parse_structured_blocks",
    "profile_policy",
    "render_plain_text",
    "run_bounded_hermes_research",
    "stable_hash",
    "transcript_projection",
    "tts_projection",
    "vexira_fixture_evidence",
    "write_validate_repair",
    "writer_payload",
]
