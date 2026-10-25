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
    ClaimAssertion,
    DeliveryMetadata,
    EvidenceRecord,
    GenerationMetadata,
    NarrativeBeat,
    NarrativeBlock,
    SceneChange,
    TurnPresentationRequest,
    ValidationReport,
    stable_hash,
)
from .delivery import InMemoryNarrativeDeliveryRepository, NarrativeDeliveryConflict, NarrativeDeliveryCoordinator
from .evidence import EvidenceAccessContext, EvidenceBroker, EvidenceGrantSet, EvidenceQuery, InMemoryEvidenceSource
from .fixtures import bran_fixture_evidence, narrative_fixture_evidence, vexira_fixture_evidence
from .hermes_research import (
    HermesResearchPolicy,
    HermesResearchRequest,
    HermesResearchResult,
    normalize_hermes_research,
    run_bounded_hermes_research,
)
from .idempotent_service import NarrativeEngineService, NarrativeTurnIdentityConflict
from .planner import DeterministicBeatPlanner, NarrativePlan
from .projections import canonical_consumer_bundle, legacy_response_projection, transcript_projection, tts_projection
from .renderer import CanonicalNarrativeRenderer
from .repository import InMemoryNarrativeResponseRepository, NarrativeResponseConflict
from .scene_change import detect_scene_changes
from .serialization import canonical_response_from_dict
from .validation import NarrativeValidator, write_validate_repair
from .world_forge import WorldForgeProposal, apply_world_forge_proposal, audit_world_forge_proposal
from .writer import (
    DeterministicNarrativeWriter,
    NarrativeWriter,
    StructuredNarrativeWriter,
    WriterResult,
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
    "ClaimAssertion",
    "DeliveryMetadata",
    "DeliveryMode",
    "DeterministicBeatPlanner",
    "DeterministicNarrativeWriter",
    "EvidenceAccessContext",
    "EvidenceBroker",
    "EvidenceGrantSet",
    "EvidenceQuery",
    "EvidenceRecord",
    "GenerationMetadata",
    "HermesResearchPolicy",
    "HermesResearchRequest",
    "HermesResearchResult",
    "InMemoryEvidenceSource",
    "InMemoryNarrativeDeliveryRepository",
    "InMemoryNarrativeResponseRepository",
    "NarrativeBeat",
    "NarrativeBlock",
    "NarrativeDeliveryConflict",
    "NarrativeDeliveryCoordinator",
    "NarrativeEngineService",
    "NarrativePlan",
    "NarrativeResponseConflict",
    "NarrativeSignificance",
    "NarrativeTurnIdentityConflict",
    "NarrativeValidator",
    "NarrativeWriter",
    "PresentationProfile",
    "SceneChange",
    "StructuredNarrativeWriter",
    "TurnPresentationRequest",
    "ValidationReport",
    "VisibilityClass",
    "WorldForgeProposal",
    "WriterResult",
    "apply_world_forge_proposal",
    "audit_world_forge_proposal",
    "bran_fixture_evidence",
    "campaign_bible_evidence",
    "canonical_consumer_bundle",
    "canonical_response_from_dict",
    "detect_scene_changes",
    "legacy_response_projection",
    "narrative_fixture_evidence",
    "normalize_hermes_research",
    "run_bounded_hermes_research",
    "stable_hash",
    "transcript_projection",
    "tts_projection",
    "vexira_fixture_evidence",
    "write_validate_repair",
    "writer_payload",
]
