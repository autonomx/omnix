from __future__ import annotations

from datetime import datetime, timezone

from .research.fact_repository import TradingFactRepository, default_fact_repository
from .research.policy import ResearchPolicyDecision, evaluate_research_policy


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
    validation = repository.latest_validation_report(policy_version)
    return evaluate_research_policy(
        strategy_version=strategy_version,
        features=features,
        validation=validation,
        policy_version=policy_version,
    )


__all__ = ["resolve_strategy_research_policy"]
