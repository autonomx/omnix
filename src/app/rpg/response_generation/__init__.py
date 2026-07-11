"""Canonical RPG response-generation contracts and policies.

Simulation remains authoritative. Modules in this package operate on presentation
contracts, evidence, proposals, validation, rendering, and approved delivery only.
"""

from .baseline import (
    BaselineMetrics,
    BaselineObservation,
    BaselineScenario,
    evaluate_baseline,
    load_baseline_scenarios,
    validate_scenarios,
)
from .candidate_ranker import CandidateRanker, NoEligibleCandidateError
from .contracts import (
    AgencyEffect,
    CandidateSource,
    GateDecision,
    RenderedResponse,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    Reversibility,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from .eligibility import EligibilityPolicy, eligibility_reasons
from .orchestration import (
    RpgResponseGenerator,
    build_runtime_shadow_report,
    build_world_scene_shadow_report,
    semantic_plan_from_legacy_payload,
)
from .quality_gate import QualityGate, QualityReport
from .renderer import ResponseRenderer

__all__ = [
    "AgencyEffect",
    "BaselineMetrics",
    "BaselineObservation",
    "BaselineScenario",
    "CandidateRanker",
    "CandidateSource",
    "EligibilityPolicy",
    "GateDecision",
    "NoEligibleCandidateError",
    "QualityGate",
    "QualityReport",
    "RenderedResponse",
    "ResponseCandidate",
    "ResponseMode",
    "ResponseRenderer",
    "ResponseRequest",
    "Reversibility",
    "RpgResponseGenerator",
    "SectionType",
    "SemanticResponsePlan",
    "SemanticSection",
    "build_runtime_shadow_report",
    "build_world_scene_shadow_report",
    "eligibility_reasons",
    "evaluate_baseline",
    "load_baseline_scenarios",
    "semantic_plan_from_legacy_payload",
    "validate_scenarios",
]
