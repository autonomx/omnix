from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .contracts import ResearchValidationReport, StrategyResearchFeatures


class ResearchPolicyDecision(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True)
    allowed: bool
    authoritative: bool
    reason_code: str
    score_adjustment: int=0
    policy_version: str


def evaluate_research_policy(*, strategy_version: str, features: StrategyResearchFeatures | None,
                             validation: ResearchValidationReport | None, policy_version: str="trading-research-1") -> ResearchPolicyDecision:
    if strategy_version in {"1.0.0","1.1.0"}:
        return ResearchPolicyDecision(allowed=True,authoritative=False,reason_code="LEGACY_RESEARCH_NON_AUTHORITATIVE",policy_version="legacy-1")
    if strategy_version != "1.2.0":
        return ResearchPolicyDecision(allowed=False,authoritative=True,reason_code="UNSUPPORTED_RESEARCH_STRATEGY_VERSION",policy_version=policy_version)
    if validation is None or validation.policy_version!=policy_version or not validation.promotion_allowed:
        return ResearchPolicyDecision(allowed=False,authoritative=True,reason_code="RESEARCH_POLICY_NOT_VALIDATED",policy_version=policy_version)
    if features is None:
        return ResearchPolicyDecision(allowed=False,authoritative=True,reason_code="RESEARCH_FEATURES_UNAVAILABLE",policy_version=policy_version)
    score=0
    for result in validation.feature_results:
        value=getattr(features,result.feature,None)
        if result.recommendation=="hard_gate":
            if result.feature in {"immediate_supply_risk","unresolved_supply"} and value is True:
                return ResearchPolicyDecision(allowed=False,authoritative=True,reason_code=f"RESEARCH_HARD_GATE_{result.feature.upper()}",policy_version=policy_version)
            if result.feature in {"primary_catalyst_confirmed","catalyst_same_day","source_authority_sufficient"} and value is not True:
                return ResearchPolicyDecision(allowed=False,authoritative=True,reason_code=f"RESEARCH_HARD_GATE_{result.feature.upper()}",policy_version=policy_version)
        elif result.recommendation in {"score_only","soft_gate"}:
            positive=(value is True and result.feature not in {"immediate_supply_risk","unresolved_supply"}) or (value is False and result.feature in {"immediate_supply_risk","unresolved_supply"})
            score += 1 if positive else -1
    return ResearchPolicyDecision(allowed=True,authoritative=True,reason_code="RESEARCH_POLICY_PASS",score_adjustment=score,policy_version=policy_version)
