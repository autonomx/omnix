from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from .research.fact_repository import TradingFactRepository, default_fact_repository
from .research.policy import ResearchPolicyDecision, evaluate_research_policy


class ResearchQualityDecision(BaseModel):
    """Shared quality projection used by AUTO PAPER and historical replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    authoritative: bool
    reason_code: str
    policy_version: str
    base_quality_score: int
    adjusted_quality_score: int
    minimum_quality_score: int
    score_adjustment: int = 0


def apply_research_policy_to_quality(
    decision: ResearchPolicyDecision,
    *,
    base_quality_score: int,
    minimum_quality_score: int,
) -> ResearchQualityDecision:
    """Apply a reviewed HTR score/gate decision to deterministic setup quality.

    Direct hard-gate failures remain failures. Otherwise the reviewed score/soft
    gate adjustment is applied to the existing 0-10 setup-quality scale, and the
    same minimum-quality threshold is used in AUTO PAPER and backtests. Legacy
    1.0/1.1 decisions are non-authoritative and therefore leave quality unchanged.
    """

    base = max(0, min(10, int(base_quality_score)))
    minimum = max(0, min(10, int(minimum_quality_score)))

    if not decision.authoritative:
        return ResearchQualityDecision(
            allowed=decision.allowed,
            authoritative=False,
            reason_code=decision.reason_code,
            policy_version=decision.policy_version,
            base_quality_score=base,
            adjusted_quality_score=base,
            minimum_quality_score=minimum,
            score_adjustment=0,
        )

    adjustment = int(decision.score_adjustment)
    adjusted = max(0, min(10, base + adjustment))

    if not decision.allowed:
        return ResearchQualityDecision(
            allowed=False,
            authoritative=True,
            reason_code=decision.reason_code,
            policy_version=decision.policy_version,
            base_quality_score=base,
            adjusted_quality_score=adjusted,
            minimum_quality_score=minimum,
            score_adjustment=adjustment,
        )

    if adjusted < minimum:
        return ResearchQualityDecision(
            allowed=False,
            authoritative=True,
            reason_code="RESEARCH_ADJUSTED_QUALITY_BELOW_MINIMUM",
            policy_version=decision.policy_version,
            base_quality_score=base,
            adjusted_quality_score=adjusted,
            minimum_quality_score=minimum,
            score_adjustment=adjustment,
        )

    return ResearchQualityDecision(
        allowed=True,
        authoritative=True,
        reason_code=decision.reason_code,
        policy_version=decision.policy_version,
        base_quality_score=base,
        adjusted_quality_score=adjusted,
        minimum_quality_score=minimum,
        score_adjustment=adjustment,
    )


def resolve_strategy_research_policy(
    *,
    strategy_version: str,
    instrument_id: str,
    decision_at: datetime,
    fact_repository: TradingFactRepository | None = None,
    policy_version: str = "trading-research-1",
) -> ResearchPolicyDecision:
    """Resolve the same causal HTR policy for AUTO PAPER and backtests.

    Versions 1.0/1.1 deliberately avoid any repository read and preserve their
    historical research-non-authoritative behavior exactly. Version 1.2 is
    fail-closed: it sees only features persisted no later than ``decision_at``
    and requires a separately reviewed validation artifact that explicitly
    permits promotion.
    """

    if decision_at.tzinfo is None:
        raise ValueError("research_policy_decision_at_must_be_timezone_aware")
    decision = decision_at.astimezone(timezone.utc)

    if strategy_version in {"1.0.0", "1.1.0"}:
        return evaluate_research_policy(
            strategy_version=strategy_version,
            features=None,
            validation=None,
            policy_version="legacy-1",
        )

    repository = fact_repository or default_fact_repository()
    features = repository.research_features_as_of(instrument_id, decision)
    validation = repository.promoted_validation_report(policy_version)
    return evaluate_research_policy(
        strategy_version=strategy_version,
        features=features,
        validation=validation,
        policy_version=policy_version,
    )


__all__ = [
    "ResearchQualityDecision",
    "apply_research_policy_to_quality",
    "resolve_strategy_research_policy",
]
