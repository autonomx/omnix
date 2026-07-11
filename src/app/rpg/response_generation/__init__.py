"""Canonical RPG response-generation contracts and policies.

Simulation remains authoritative. Modules in this package operate on presentation
contracts, evidence, proposals, validation, rendering, and approved delivery only.
"""

from .baseline import BaselineMetrics, BaselineObservation, BaselineScenario, evaluate_baseline, load_baseline_scenarios, validate_scenarios
from .candidate_ranker import CandidateRanker, NoEligibleCandidateError
from .claim_ledger import ClaimLedger, ClaimRecord, derive_claim_ledger
from .context_compiler import ContextTrace, EvidenceCard, NarrationContext, NarrationContextCompiler
from .contracts import AgencyEffect, CandidateSource, GateDecision, RenderedResponse, ResponseCandidate, ResponseMode, ResponseRequest, Reversibility, SectionType, SemanticResponsePlan, SemanticSection
from .eligibility import EligibilityPolicy, eligibility_reasons
from .fallback_library import DeterministicFallbackLibrary, FallbackInput
from .forward_motion import ForwardMotionPlan, ForwardMotionPolicy, RecoveryHistoryEntry, validate_agency
from .intent_affordance import IntentAnalysis, IntentHypothesis, NarrativeAffordanceClassifier
from .orchestration import RpgResponseGenerator, build_runtime_shadow_report, build_world_scene_shadow_report, semantic_plan_from_legacy_payload
from .quality_gate import QualityGate, QualityReport
from .recovery import LocalRecoveryAnalysis, LocalRecoveryCoordinator
from .renderer import ResponseRenderer
from .retrieval import EvidenceRecord, LocalKnowledgeRetriever, RetrievalResult, build_retrieval_sources
from .semantic_plan import SemanticPlanValidation, validate_semantic_plan

__all__ = [
    "AgencyEffect", "BaselineMetrics", "BaselineObservation", "BaselineScenario",
    "CandidateRanker", "CandidateSource", "ClaimLedger", "ClaimRecord", "ContextTrace",
    "DeterministicFallbackLibrary", "EligibilityPolicy", "EvidenceCard", "EvidenceRecord",
    "FallbackInput", "ForwardMotionPlan", "ForwardMotionPolicy", "GateDecision",
    "IntentAnalysis", "IntentHypothesis", "LocalKnowledgeRetriever", "LocalRecoveryAnalysis",
    "LocalRecoveryCoordinator", "NarrationContext", "NarrationContextCompiler",
    "NarrativeAffordanceClassifier", "NoEligibleCandidateError", "QualityGate", "QualityReport",
    "RecoveryHistoryEntry", "RenderedResponse", "ResponseCandidate", "ResponseMode",
    "ResponseRenderer", "ResponseRequest", "RetrievalResult", "Reversibility",
    "RpgResponseGenerator", "SectionType", "SemanticPlanValidation", "SemanticResponsePlan",
    "SemanticSection", "build_retrieval_sources", "build_runtime_shadow_report",
    "build_world_scene_shadow_report", "derive_claim_ledger", "eligibility_reasons",
    "evaluate_baseline", "load_baseline_scenarios", "semantic_plan_from_legacy_payload",
    "validate_agency", "validate_scenarios", "validate_semantic_plan",
]
