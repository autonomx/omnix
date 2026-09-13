"""VoiceMem-derived Omnix Memory v2 contract surface.

Memory v2 is contract-first.  Importing this package does not enable v2 authority or
change the existing assistant_memory runtime.
"""

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
    "ConsolidationReceipt",
    "CutoverReadiness",
    "Episode",
    "GraphAssertion",
    "GraphEntityRef",
    "GraphValue",
    "MemoryAuthorityEpoch",
    "MemoryGrant",
    "MemorySpaceKey",
    "MemoryWatermarks",
    "Observation",
    "ObservationDisposition",
    "ObservationProvenance",
    "RelationshipMetric",
    "RelationshipState",
    "RetrievalCandidate",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalScore",
    "VisibilityScope",
]
