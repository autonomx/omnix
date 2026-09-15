"""Continuous Companion Activity Runtime."""

from .authority import (
    ActivityAuthoritySource,
    ActivityFieldPolicy,
    DEFAULT_ACTIVITY_FIELD_POLICIES,
    activity_field_policy,
    authority_source_for,
)
from .contracts import (
    EvidenceInheritedPolicy,
    EvidenceLink,
    EvidenceProposition,
    EvidenceRelation,
    EvidenceSourceKind,
    TRUST_BEARING_RELATIONS,
    derive_proposition,
    inherit_evidence_policy,
)
from .progress import ActivityProgressReducer, PROGRESS_PREDICATES
from .reducer import ActivityReducer
from .runtime import ActivityRuntimeResult, CompanionActivityRuntime
from .state import (
    ActivityField,
    ActivityMeaningfulEvent,
    ActivityOpenLoop,
    ActivityProgressMarker,
    ActivityReductionResult,
    ActivityStateChange,
    ActivityStrategyChange,
    ActivityTransitionCandidate,
    CompanionActivityState,
    OpenLoopStatus,
    empty_activity_state,
)

__all__ = [
    "ActivityAuthoritySource",
    "ActivityField",
    "ActivityFieldPolicy",
    "ActivityMeaningfulEvent",
    "ActivityOpenLoop",
    "ActivityProgressMarker",
    "ActivityProgressReducer",
    "ActivityReducer",
    "ActivityReductionResult",
    "ActivityRuntimeResult",
    "ActivityStateChange",
    "ActivityStrategyChange",
    "ActivityTransitionCandidate",
    "CompanionActivityRuntime",
    "CompanionActivityState",
    "DEFAULT_ACTIVITY_FIELD_POLICIES",
    "EvidenceInheritedPolicy",
    "EvidenceLink",
    "EvidenceProposition",
    "EvidenceRelation",
    "EvidenceSourceKind",
    "OpenLoopStatus",
    "PROGRESS_PREDICATES",
    "TRUST_BEARING_RELATIONS",
    "activity_field_policy",
    "authority_source_for",
    "derive_proposition",
    "empty_activity_state",
    "inherit_evidence_policy",
]
