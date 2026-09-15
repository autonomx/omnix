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
from .reducer import ActivityReducer
from .state import (
    ActivityField,
    ActivityReductionResult,
    ActivityStateChange,
    ActivityTransitionCandidate,
    CompanionActivityState,
    empty_activity_state,
)

__all__ = [
    "ActivityAuthoritySource",
    "ActivityField",
    "ActivityFieldPolicy",
    "ActivityReducer",
    "ActivityReductionResult",
    "ActivityStateChange",
    "ActivityTransitionCandidate",
    "CompanionActivityState",
    "DEFAULT_ACTIVITY_FIELD_POLICIES",
    "EvidenceInheritedPolicy",
    "EvidenceLink",
    "EvidenceProposition",
    "EvidenceRelation",
    "EvidenceSourceKind",
    "TRUST_BEARING_RELATIONS",
    "activity_field_policy",
    "authority_source_for",
    "derive_proposition",
    "empty_activity_state",
    "inherit_evidence_policy",
]
