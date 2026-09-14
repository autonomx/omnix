"""VoiceMem-derived Omnix Memory v2 contract surface.

Memory v2 is contract-first. Importing this package does not enable v2 authority or
change the existing assistant_memory runtime.
"""

from .authority import (
    AuthorityEpochState,
    CutoverNotReadyError,
    MemoryAuthorityError,
    PostgresMemoryV2AuthorityStore,
    SpaceCutoverReadinessReceipt,
    StaleCutoverReceiptError,
)
from .contracts import (
    SYSTEM_MEMORY_OWNER_ID,
    AffectObservation,
    ConsolidationReceipt,
    CutoverReadiness,
    Episode,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryAuthorityEpoch,
    MemoryGrant,
    MemorySpaceKey,
    MemoryWatermarks,
    Observation,
    ObservationDisposition,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalResult,
    RetrievalScore,
    VisibilityScope,
)

__all__ = [
    "SYSTEM_MEMORY_OWNER_ID",
    "AffectObservation",
    "AuthorityEpochState",
    "ConsolidationReceipt",
    "CutoverNotReadyError",
    "CutoverReadiness",
    "Episode",
    "GraphAssertion",
    "GraphEntityRef",
    "GraphValue",
    "MemoryAuthorityEpoch",
    "MemoryAuthorityError",
    "MemoryGrant",
    "MemorySpaceKey",
    "MemoryWatermarks",
    "Observation",
    "ObservationDisposition",
    "ObservationProvenance",
    "PostgresMemoryV2AuthorityStore",
    "RelationshipMetric",
    "RelationshipState",
    "RetrievalCandidate",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalScore",
    "SpaceCutoverReadinessReceipt",
    "StaleCutoverReceiptError",
    "VisibilityScope",
]
